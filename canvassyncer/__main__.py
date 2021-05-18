import argparse
import asyncio
import json
import ntpath
import os
import re
import time
import traceback
from datetime import datetime, timezone

import aiofiles
import aiohttp
from tqdm import tqdm

__version__ = "2.0.5"
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".canvassyncer.json"
)
PAGES_PER_TIME = 8


class AsyncDownloader:
    def __init__(self, sess, sem, config):
        self.sess: aiohttp.ClientSession = sess
        self.sem = sem
        self.config = config

    async def downloadOne(self, src, dst):
        async with self.sem:
            async with self.sess.get(src, proxy=self.config.get("proxies")) as res:
                if res.status != 200:
                    return self.failures.append(f"{src} => {dst}")
                async with aiofiles.open(dst, "+wb") as f:
                    while True:
                        chunk = await res.content.read(1024 * 4)
                        if not chunk:
                            break
                        await f.write(chunk)
                        self.tqdm.update(len(chunk))

    async def start(self, infos, totalSize=0):
        self.tqdm = tqdm(total=totalSize, unit="B", unit_scale=True)
        self.failures = []
        await asyncio.gather(
            *[asyncio.create_task(self.downloadOne(src, dst)) for src, dst in infos]
        )
        self.tqdm.close()
        if self.failures:
            print(f"Fail to download these {len(self.failures)} file(s):")
            for text in self.failures:
                print(text)


class CanvasSyncer:
    def __init__(self, config):
        self.confirmAll = config["y"]
        self.config = config
        self.sess = aiohttp.ClientSession()
        self.sem = asyncio.Semaphore(config["connection_count"])
        self.downloadSize = 0
        self.laterDownloadSize = 0
        self.courseCode = {}
        self.baseurl = self.config["canvasURL"] + "/api/v1"
        self.downloadDir = self.config["downloadDir"]
        self.newInfo = []
        self.newFiles = []
        self.laterFiles = []
        self.laterInfo = []
        self.skipfiles = []
        self.downloader = AsyncDownloader(self.sess, self.sem, self.config)
        if not os.path.exists(self.downloadDir):
            os.mkdir(self.downloadDir)

    async def close(self):
        await self.sess.close()

    def setSessionArgs(self, **kwargs):
        kwargs["timeout"] = kwargs.get("timeout", 10)
        kwargs["headers"] = kwargs.get("headers", {})
        kwargs["headers"]["Authorization"] = f"Bearer {self.config['token']}"
        kwargs["proxy"] = self.config.get("proxies")
        return kwargs

    async def sessGetJson(self, *args, **kwargs):
        async with self.sem:
            async with self.sess.get(*args, **self.setSessionArgs(**kwargs)) as resp:
                return await resp.json()

    async def sessHead(self, *args, **kwargs):
        async with self.sem:
            async with self.sess.head(*args, **self.setSessionArgs(**kwargs)) as resp:
                return resp.headers

    def prepareLocalFiles(self, courseID, folders):
        localFiles = []
        for folder in folders.values():
            if self.config["no_subfolder"]:
                path = os.path.join(self.downloadDir, folder[1:])
            else:
                path = os.path.join(
                    self.downloadDir, f"{self.courseCode[courseID]}{folder}"
                )
            if not os.path.exists(path):
                os.makedirs(path)
            localFiles += [
                os.path.join(folder, f).replace("\\", "/").replace("//", "/")
                for f in os.listdir(path)
                if not os.path.isdir(os.path.join(path, f))
            ]
        return localFiles

    async def getCourseFoldersWithIDHelper(self, courseID, page):
        res = {}
        url = f"{self.baseurl}/courses/{courseID}/folders?page={page}"
        folders = await self.sessGetJson(url)
        for folder in folders:
            if folder["full_name"].startswith("course files"):
                folder["full_name"] = folder["full_name"][len("course files") :]
            res[folder["id"]] = folder["full_name"]
            if not res[folder["id"]]:
                res[folder["id"]] = "/"
            res[folder["id"]] = re.sub(r"[\\\:\*\?\"\<\>\|]", "_", res[folder["id"]])
        return res

    async def getCourseFoldersWithID(self, courseID):
        folders = {}
        page = 1
        endOfPage = False
        while not endOfPage:
            pageRes = await asyncio.gather(
                *[
                    self.getCourseFoldersWithIDHelper(courseID, page + i)
                    for i in range(PAGES_PER_TIME)
                ]
            )
            for item in pageRes:
                if not item:
                    endOfPage = True
                folders.update(item)
            page += PAGES_PER_TIME
        return folders

    async def getCourseFilesHelper(self, courseID, page, folders):
        files = {}
        url = f"{self.baseurl}/courses/{courseID}/files?page={page}"
        canvasFiles = await self.sessGetJson(url)
        if not canvasFiles or isinstance(canvasFiles, dict):
            return files
        for f in canvasFiles:
            if f["folder_id"] not in folders.keys():
                continue
            f["display_name"] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", f["display_name"])
            path = f"{folders[f['folder_id']]}/{f['display_name']}"
            path = path.replace("\\", "/").replace("//", "/")
            dt = datetime.strptime(f["modified_at"], "%Y-%m-%dT%H:%M:%SZ")
            modifiedTimeStamp = dt.replace(tzinfo=timezone.utc).timestamp()
            files[path] = (f["url"], int(modifiedTimeStamp))
        return files

    async def getCourseFiles(self, courseID):
        files = {}
        page = 1
        folders = await self.getCourseFoldersWithID(courseID)
        endOfPage = False
        while not endOfPage:
            pageRes = await asyncio.gather(
                *[
                    self.getCourseFilesHelper(courseID, page + i, folders)
                    for i in range(PAGES_PER_TIME)
                ]
            )
            for item in pageRes:
                if not item:
                    endOfPage = True
                files.update(item)
            page += PAGES_PER_TIME
        return folders, files

    async def getCourseIdByCourseCodeHelper(self, page, lowerCourseCodes):
        res = {}
        url = f"{self.baseurl}/courses?page={page}"
        courses = await self.sessGetJson(url)
        if isinstance(courses, dict) and courses.get("errors"):
            errMsg = courses["errors"][0].get("message", "unknown error.")
            print(f"\nError: {errMsg}")
            exit(1)
        if not courses:
            return res
        for course in courses:
            if course.get("course_code", "").lower() in lowerCourseCodes:
                res[course["id"]] = course["course_code"]
                lowerCourseCodes.remove(course.get("course_code", "").lower())
        return res

    async def getCourseIdByCourseCode(self):
        page = 1
        lowerCourseCodes = [s.lower() for s in self.config["courseCodes"]]
        endOfPage = False
        while not endOfPage:
            pageRes = await asyncio.gather(
                *[
                    self.getCourseIdByCourseCodeHelper(page + i, lowerCourseCodes)
                    for i in range(PAGES_PER_TIME)
                ]
            )
            for item in pageRes:
                if not item:
                    endOfPage = True
                self.courseCode.update(item)
            page += PAGES_PER_TIME

    async def getCourseCodeByCourseIDHelper(self, courseID):
        url = f"{self.baseurl}/courses/{courseID}"
        sessRes = await self.sessGetJson(url)
        if sessRes.get("course_code") is None:
            return
        self.courseCode[courseID] = sessRes["course_code"]

    async def getCourseCodeByCourseID(self):
        await asyncio.gather(
            *[
                asyncio.create_task(self.getCourseCodeByCourseIDHelper(courseID))
                for courseID in self.config["courseIDs"]
            ]
        )

    async def getCourseID(self):
        coros = []
        if self.config.get("courseCodes"):
            coros.append(self.getCourseIdByCourseCode())
        if self.config.get("courseIDs"):
            coros.append(self.getCourseCodeByCourseID())
        await asyncio.gather(*coros)

    async def getCourseTaskInfoHelper(
        self, courseID, localFiles, fileName, fileUrl, fileModifiedTimeStamp
    ):
        if not fileUrl:
            return
        if self.config["no_subfolder"]:
            path = os.path.join(self.downloadDir, fileName[1:])
        else:
            path = os.path.join(
                self.downloadDir, f"{self.courseCode[courseID]}{fileName}"
            )
        path = path.replace("\\", "/").replace("//", "/")
        if fileName in localFiles and fileModifiedTimeStamp <= os.path.getctime(path):
            return
        response = await self.sessHead(fileUrl)
        fileSize = int(response.get("content-length", 0))
        if fileName in localFiles:
            self.laterDownloadSize += fileSize
            self.laterFiles.append((fileUrl, path))
            self.laterInfo.append(
                f"{self.courseCode[courseID]}{fileName} ({round(fileSize / 1000000, 2)}MB)"
            )
            return
        if fileSize > self.config["filesizeThresh"] * 1000000:
            print(
                f"{self.courseCode[courseID]}{fileName} ({round(fileSize / 1000000, 2)}MB) ignored, too large."
            )
            aiofiles.open(path, "w").close()
            self.skipfiles.append(
                f"{self.courseCode[courseID]}{fileName} ({round(fileSize / 1000000, 2)}MB)"
            )
            return
        self.newInfo.append(
            f"{self.courseCode[courseID]}{fileName} ({round(fileSize / 1000000, 2)}MB)"
        )
        self.downloadSize += fileSize
        self.newFiles.append((fileUrl, path))

    async def getCourseTaskInfo(self, courseID):
        folders, files = await self.getCourseFiles(courseID)
        localFiles = self.prepareLocalFiles(courseID, folders)
        await asyncio.gather(
            *[
                self.getCourseTaskInfoHelper(
                    courseID, localFiles, fileName, fileUrl, fileModifiedTimeStamp
                )
                for fileName, (fileUrl, fileModifiedTimeStamp) in files.items()
            ]
        )

    def checkNewFiles(self):
        if self.skipfiles:
            print(
                "These file(s) will not be synced due to their size"
                + f" (over {self.config['filesizeThresh']} MB):"
            )
            for f in self.skipfiles:
                print(f)
        if self.newFiles:
            print(f"Start to download {len(self.newInfo)} file(s)!")
            for s in self.newInfo:
                print(s)

    def checkLaterFiles(self):
        if not self.laterFiles:
            return
        print("These file(s) have later version on canvas:")
        for s in self.laterInfo:
            print(s)
        isDownload = "Y" if self.confirmAll else input("Update all?(Y/n) ")
        if isDownload in ["n", "N"]:
            return
        print(f"Start to download {len(self.laterInfo)} file(s)!")
        laterFiles = []
        for (fileUrl, path) in self.laterFiles:
            localCreatedTimeStamp = int(os.path.getctime(path))
            try:
                newPath = os.path.join(
                    ntpath.dirname(path),
                    f"{localCreatedTimeStamp}_{ntpath.basename(path)}",
                )
                if not os.path.exists(newPath):
                    os.rename(path, newPath)
                else:
                    path = os.path.join(
                        ntpath.dirname(path),
                        f"{int(time.time())}_{ntpath.basename(path)}",
                    )
                laterFiles.append((fileUrl, path))
            except Exception as e:
                print(f"{e.__class__.__name__}! Skipped: {path}")
        self.laterFiles = laterFiles

    async def sync(self):
        print("Getting course IDs...")
        await self.getCourseID()
        print(f"Get {len(self.courseCode)} available courses!")
        print("Finding files on canvas...")
        await asyncio.gather(
            *[
                asyncio.create_task(self.getCourseTaskInfo(courseID))
                for courseID in self.courseCode.keys()
            ]
        )
        if not self.newFiles and not self.laterFiles:
            return print("All local files are synced!")
        self.checkNewFiles()
        self.checkLaterFiles()
        await self.downloader.start(
            self.newFiles + self.laterFiles, self.downloadSize + self.laterDownloadSize
        )


def initConfig():
    oldConfig = {}
    if os.path.exists(CONFIG_PATH):
        oldConfig = json.load(open(CONFIG_PATH))
    elif os.path.exists("./canvassyncer.json"):
        oldConfig = json.load(open("./canvassyncer.json"))
    print("Generating new config file...")
    url = input("Canvas url(Default: https://umjicanvas.com):").strip()
    if not url:
        url = "https://umjicanvas.com"
    tipStr = f"(Default: {oldConfig.get('token', '')})" if oldConfig else ""
    token = input(f"Canvas access token{tipStr}:").strip()
    if not token:
        token = oldConfig.get("token", "")
    tipStr = (
        f"(Default: {' '.join(oldConfig.get('courseCodes', []))})" if oldConfig else ""
    )
    courseCodes = (
        input(f"Courses to sync in course codes(split with space){tipStr}:")
        .strip()
        .split()
    )
    if not courseCodes:
        courseCodes = oldConfig.get("courseCodes", [])
    tipStr = (
        f"(Default: {' '.join([str(item) for item in oldConfig.get('courseIDs', [])])})"
        if oldConfig
        else ""
    )
    courseIDs = (
        input(f"Courses to sync in course ID(split with space){tipStr}:")
        .strip()
        .split()
    )
    if not courseIDs:
        courseIDs = oldConfig.get("courseIDs", [])
    courseIDs = [int(courseID) for courseID in courseIDs]
    tipStr = f"(Default: {oldConfig.get('downloadDir', os.path.abspath(''))})"
    downloadDir = input(f"Path to save canvas files{tipStr}:").strip()
    if not downloadDir:
        downloadDir = oldConfig.get("downloadDir", os.path.abspath(""))
    tipStr = (
        f"(Default: {oldConfig.get('filesizeThresh', '')})"
        if oldConfig
        else f"(Default: 250)"
    )
    filesizeThresh = input(f"Maximum file size to download(MB){tipStr}:").strip()
    try:
        filesizeThresh = float(filesizeThresh)
    except Exception:
        filesizeThresh = 250
    json.dump(
        {
            "canvasURL": url,
            "token": token,
            "courseCodes": courseCodes,
            "courseIDs": courseIDs,
            "downloadDir": downloadDir,
            "filesizeThresh": filesizeThresh,
        },
        open(CONFIG_PATH, mode="w", encoding="utf-8"),
        indent=4,
    )


async def sync():
    Syncer, args = None, None
    try:
        parser = argparse.ArgumentParser(description="A Simple Canvas File Syncer")
        parser.add_argument("-r", help="recreate config file", action="store_true")
        parser.add_argument("-y", help="confirm all prompts", action="store_true")
        parser.add_argument(
            "--no-subfolder",
            help="do not create a course code named subfolder when synchronizing files",
            action="store_true",
        )
        parser.add_argument(
            "-p", "--path", help="appoint config file path", default=CONFIG_PATH
        )
        parser.add_argument(
            "-c",
            "--connection",
            help="max connection count with server",
            default=16,
            type=int,
        )
        parser.add_argument("-x", "--proxy", help="download proxy", default=None)
        parser.add_argument("-V", "--version", action="version", version=__version__)
        parser.add_argument(
            "-d", "--debug", help="show debug information", action="store_true"
        )
        args = parser.parse_args()
        configPath = args.path
        if args.r or not os.path.exists(configPath):
            if not os.path.exists(configPath):
                print("Config file not exist, creating...")
            try:
                initConfig()
            except Exception as e:
                print(f"\nError: {e.__class__.__name__}. Failed to create config file.")
                if args.debug:
                    print(traceback.format_exc())
                exit(1)
            if args.r:
                return
        config = json.load(open(configPath, "r", encoding="UTF-8"))
        config["y"] = args.y
        config["proxies"] = args.proxy
        config["no_subfolder"] = args.no_subfolder
        config["connection_count"] = args.connection
        Syncer = CanvasSyncer(config)
        await Syncer.sync()
    except aiohttp.ServerDisconnectedError as e:
        print("Server disconnected error, try to reduce connection count using -c")
        exit(1)
    except KeyboardInterrupt as e:
        raise (e)
    except Exception as e:
        errorName = e.__class__.__name__
        print(f"Unexpected error: {errorName}. Please check your network and token! Or use -d for detailed information.")
        if args.debug:
            print(traceback.format_exc())
    finally:
        await Syncer.close()


def run():
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        asyncio.get_event_loop().run_until_complete(sync())
    except KeyboardInterrupt as e:
        print("\nOperation cancelled by user, exiting...")
        exit(1)


if __name__ == "__main__":
    run()

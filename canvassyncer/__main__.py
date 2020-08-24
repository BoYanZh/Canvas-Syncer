import argparse
import json
import os
import pkg_resources
import re
import requests
import requests.exceptions
import threading
import time
import urllib3.exceptions
from datetime import timezone, datetime
from functools import partial
from queue import Queue
from requests.adapters import HTTPAdapter
from threading import Thread
from urllib3.util.retry import Retry
from tqdm import tqdm
import ntpath

__version__ = pkg_resources.require("canvassyncer")[0].version
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".canvassyncer.json")
MAX_DOWNLOAD_COUNT = 8
_sentinel = object()

print = partial(print, flush=True)


class MultithreadDownloaderStop(BaseException):
    pass


class MultithreadDownloader:
    blockSize = 512

    def __init__(self, session, maxThread):
        self.sess = session
        self.maxThread = maxThread
        self.currentDownload = []
        self.countLock = threading.Lock()
        self.taskQueue = Queue()
        self.downloadedCnt = 0
        self.totalCnt = 0
        self.totalSize = 0
        self.tqdm = None
        self.stopSignal = False

    def downloadFile(self, i, queue):
        while True:
            if self.stopSignal:
                self.downloadedCnt = self.totalCnt
                break
            src, dst = queue.get()
            if src is _sentinel:
                queue.put([src, dst])
                break
            self.currentDownload[i] = dst.split('/')[-1].split('\\')[-1]
            tmpFilePath = ''
            try:
                r = self.sess.get(src, timeout=10, stream=True)
                tmpFilePath = f"{dst}.tmp.{int(time.time())}"
                with open(tmpFilePath, 'wb') as fd:
                    for chunk in r.iter_content(
                            MultithreadDownloader.blockSize):
                        self.tqdm.update(len(chunk))
                        fd.write(chunk)
                        if self.stopSignal:
                            break
                os.rename(tmpFilePath, dst)
            except Exception as e:
                print(
                    f"\nError: {e.__class__.__name__}. Download {dst} fails!")
            finally:
                if os.path.exists(tmpFilePath):
                    os.remove(tmpFilePath)
                with self.countLock:
                    self.downloadedCnt += 1

    def init(self):
        self.taskQueue = Queue()
        self.downloadedCnt = 0
        self.totalCnt = 0
        self.downloadingFileName = 'None'
        self.totalSize = 0
        self.stopSignal = False
        self.tqdm = None
        self.currentDownload = ['' for i in range(self.maxThread)]

    def create(self, infos, totalSize=0):
        self.init()
        self.totalSize = totalSize
        self.tqdm = tqdm(total=totalSize, unit='iB', unit_scale=True)
        for src, dst in infos:
            self.taskQueue.put((src, dst))
            self.totalCnt += 1
        self.taskQueue.put((_sentinel, _sentinel))

    def start(self):
        for i in range(self.maxThread):
            t = Thread(target=self.downloadFile,
                       args=(i, self.taskQueue),
                       daemon=True)
            t.start()

    def stop(self):
        self.stopSignal = True
        if self.tqdm:
            self.tqdm.close()
        print('\nOperation cancelled by user, exiting...')
        while not self.finished:
            time.sleep(0.1)

    @property
    def finished(self):
        return self.downloadedCnt >= self.totalCnt

    def waitTillFinish(self):
        word = 'None'
        downloadingFileName = ''
        while not self.finished:
            for fileName in reversed(self.currentDownload):
                if fileName:
                    downloadingFileName = fileName
                    break
            if word not in (downloadingFileName + ' ' * 5) * 2:
                word = downloadingFileName + ' ' * 5
            if len(word) <= 20:
                self.tqdm.set_description((word + ' ' * 10)[:15])
            else:
                self.tqdm.set_description(word[:15])
            # print("\r{:5d}/{:5d} Downloading... {}".format(
            #     self.downloadedCnt, self.totalCnt, word[:15]),
            #       end='')
            if len(word) > 20:
                word = word[1:] + word[0]
            time.sleep(0.1)
        if self.tqdm:
            self.tqdm.close()
        # if self.totalCnt > 0:
        #     print("\r{:5d}/{:5d} Finish!        {}".format(
        #         self.downloadedCnt, self.totalCnt, ' ' * 15))


class CanvasSyncer:
    def __init__(self, confirmAll, settingsPath):
        self.confirmAll = confirmAll
        print(f"\rLoading settings...", end='')
        self.settings = self.loadSettings(settingsPath)
        print("\rSettings loaded!    ")
        self.sess = requests.Session()
        retryStrategy = Retry(total=5,
                              status_forcelist=[429, 500, 502, 503, 504],
                              method_whitelist=["HEAD", "GET", "OPTIONS"])
        adapter = HTTPAdapter(max_retries=retryStrategy)
        self.sess.mount("https://", adapter)
        self.sess.mount("http://", adapter)
        self.downloadSize = 0
        self.laterDownloadSize = 0
        self.courseCode = {}
        self.baseurl = self.settings['canvasURL'] + '/api/v1'
        self.downloadDir = self.settings['downloadDir']
        self.newInfo = []
        self.laterFiles = []
        self.laterInfo = []
        self.skipfiles = []
        self.filesLock = threading.Lock()
        self.taskQueue = Queue()
        self.downloader = MultithreadDownloader(self.sess, MAX_DOWNLOAD_COUNT)
        if not os.path.exists(self.downloadDir):
            os.mkdir(self.downloadDir)

    def loadSettings(self, filePath):
        return json.load(open(filePath, 'r', encoding='UTF-8'))

    def sessGet(self, *args, **kwargs):
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = 10
        if kwargs.get('header') is None:
            kwargs['headers'] = dict()
        kwargs['headers']['Authorization'] = f"Bearer {self.settings['token']}"
        try:
            return self.sess.get(*args, **kwargs)
        except (urllib3.exceptions.MaxRetryError,
                requests.exceptions.ConnectionError) as e:
            raise ConnectionError(e)

    def createFolders(self, courseID, folders):
        for folder in folders.values():
            path = os.path.join(self.downloadDir,
                                f"{self.courseCode[courseID]}{folder}")
            if not os.path.exists(path):
                os.makedirs(path)

    def getLocalFiles(self, courseID, folders):
        localFiles = []
        for folder in folders.values():
            path = os.path.join(self.downloadDir,
                                f"{self.courseCode[courseID]}{folder}")
            localFiles += [
                os.path.join(folder, f).replace('\\', '/').replace('//', '/')
                for f in os.listdir(path)
                if not os.path.isdir(os.path.join(path, f))
            ]
        return localFiles

    def getCourseFolders(self, courseID):
        return [
            folder
            for folder in self.getCourseFoldersWithID(courseID).values()
        ]

    def getCourseFoldersWithID(self, courseID):
        res = {}
        page = 1
        while True:
            url = f"{self.baseurl}/courses/{courseID}/folders?page={page}"
            folders = self.sessGet(url).json()
            if not folders:
                break
            for folder in folders:
                res[folder['id']] = folder['full_name'].replace(
                    "course files", "")
                if not res[folder['id']]:
                    res[folder['id']] = '/'
            page += 1
        return res

    def getCourseFiles(self, courseID):
        folders, res = self.getCourseFoldersWithID(courseID), {}
        page = 1
        while True:
            url = f"{self.baseurl}/courses/{courseID}/files?page={page}"
            files = self.sessGet(url).json()
            if not files:
                break
            for f in files:
                f['display_name'] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_",
                                           f['display_name'])
                path = f"{folders[f['folder_id']]}/{f['display_name']}"
                path = path.replace('\\', '/').replace('//', '/')
                dt = datetime.strptime(f["modified_at"], "%Y-%m-%dT%H:%M:%SZ")
                modifiedTimeStamp = dt.replace(tzinfo=timezone.utc).timestamp()
                res[path] = (f["url"], int(modifiedTimeStamp))
            page += 1
        return folders, res

    def getCourseCode(self, courseID):
        url = f"{self.baseurl}/courses/{courseID}"
        return self.sessGet(url).json()['course_code']

    def getCourseID(self):
        res = {}
        page = 1
        if self.settings.get('courseCodes'):
            lowerCourseCodes = [
                s.lower() for s in self.settings['courseCodes']
            ]
            while True:
                url = f"{self.baseurl}/courses?page={page}"
                courses = self.sessGet(url).json()
                if not courses:
                    break
                for course in courses:
                    if course.get('course_code',
                                  '').lower() in lowerCourseCodes:
                        res[course['id']] = course['course_code']
                        lowerCourseCodes.remove(
                            course.get('course_code', '').lower())
                page += 1
        if self.settings.get('courseIDs'):
            for courseID in self.settings['courseIDs']:
                res[courseID] = self.getCourseCode(courseID)
        return res

    def getCourseTaskInfo(self, courseID):
        folders, files = self.getCourseFiles(courseID)
        self.createFolders(courseID, folders)
        localFiles = self.getLocalFiles(courseID, folders)
        res = []
        for fileName, (fileUrl, fileModifiedTimeStamp) in files.items():
            if not fileUrl:
                continue
            path = os.path.join(self.downloadDir,
                                f"{self.courseCode[courseID]}{fileName}")
            path = path.replace('\\', '/').replace('//', '/')
            if fileName in localFiles:
                localCreatedTimeStamp = int(os.path.getctime(path))
                if fileModifiedTimeStamp <= localCreatedTimeStamp:
                    continue
                response = self.sess.head(fileUrl)
                fileSize = int(response.headers.get('content-length', 0))
                self.laterDownloadSize += fileSize
                self.laterFiles.append((fileUrl, path))
                self.laterInfo.append(
                    f"{self.courseCode[courseID]}{fileName} ({round(fileSize / 2**20, 2)}MB)"
                )
                continue
            response = self.sess.head(fileUrl)
            fileSize = int(response.headers.get('content-length', 0))
            if fileSize / 2**20 > self.settings['filesizeThresh']:
                if not self.confirmAll:
                    print(
                        f'\nTarget file: {self.courseCode[courseID]}{fileName} is too large ({round(fileSize / 2**20, 2)}MB), ignore?(Y/n) ',
                        end='')
                    isDownload = input()
                else:
                    print(
                        f'\nTarget file: {self.courseCode[courseID]}{fileName} is too large ({round(fileSize / 2**20, 2)}MB), ignore. '
                    )
                    isDownload = 'Y'
                if isDownload not in ['n', 'N']:
                    print('Creating empty file as scapegoat...')
                    open(path, 'w').close()
                    self.skipfiles.append(path)
                    continue
            self.newInfo.append(
                f"{self.courseCode[courseID]}{fileName} ({round(fileSize / 2**20, 2)}MB)"
            )
            self.downloadSize += fileSize
            res.append((fileUrl, path))
        return res

    def checkNewFiles(self):
        print("\rFinding files on canvas...", end='')
        allInfos = []
        for courseID in self.courseCode.keys():
            for info in self.getCourseTaskInfo(courseID):
                allInfos.append(info)
        if len(allInfos) == 0:
            print("\rLocal files are synced!")
        else:
            print(f"\rFind {len(allInfos)} new files!           ")
            if self.skipfiles:
                print(
                    f"The following file(s) will not be synced due to their size (over {self.settings['filesizeThresh']} MB):"
                )
                [print(f) for f in self.skipfiles]
            print(
                f"Start to download following files! Total size: {round(self.downloadSize / 2**20, 2)}MB"
            )
            [print(s) for s in self.newInfo]
            self.downloader.create(allInfos, self.downloadSize)
            self.downloader.start()
            self.downloader.waitTillFinish()

    def checkLaterFiles(self):
        if not self.laterFiles:
            return
        print("These file(s) have later version on canvas:")
        [print(s) for s in self.laterInfo]
        if not self.confirmAll:
            print('Update all?(Y/n) ', end='')
            isDownload = input()
        else:
            isDownload = 'Y'
        if isDownload in ['n', 'N']:
            return
        print(
            f"Start to download these files! Total size: {round(self.laterDownloadSize / 2**20, 2)}MB"
        )
        laterFiles = []
        for (fileUrl, path) in self.laterFiles:
            localCreatedTimeStamp = int(os.path.getctime(path))
            try:
                try:
                    newPath = os.path.join(
                        ntpath.dirname(path),
                        f"{localCreatedTimeStamp}_{ntpath.basename(path)}")
                    os.rename(path, newPath)
                except Exception as e:
                    os.remove(path)
                laterFiles.append((fileUrl, path))
            except Exception as e:
                print(f"{e.__class__.__name__}! Skipped: {path}")
        self.downloader.create(laterFiles, self.laterDownloadSize)
        self.downloader.start()
        self.downloader.waitTillFinish()

    def sync(self):
        print("\rGetting course IDs...", end='')
        self.courseCode = self.getCourseID()
        print(f"\rGet {len(self.courseCode)} available courses!")
        self.checkNewFiles()
        self.checkLaterFiles()


def initConfig():
    oldConfig = dict()
    if os.path.exists(CONFIG_PATH):
        oldConfig = json.load(open(CONFIG_PATH))
    elif os.path.exists("./canvassyncer.json"):
        oldConfig = json.load(open("./canvassyncer.json"))
    print("Generating new config file...")
    try:
        url = input("Canvas url(Default: https://umjicanvas.com):").strip()
        if not url:
            url = "https://umjicanvas.com"
        tipStr = f"(Default: {oldConfig.get('token', '')})" if oldConfig else ""
        token = input(f"Canvas access token{tipStr}:").strip()
        if not token:
            token = oldConfig.get('token', '')
        tipStr = f"(Default: {' '.join(oldConfig.get('courseCodes', list()))})" if oldConfig else ""
        courseCodes = input(
            f"Courses to sync in course codes(split with space){tipStr}:"
        ).strip().split()
        if not courseCodes:
            courseCodes = oldConfig.get('courseCodes', list())
        tipStr = f"(Default: {' '.join(oldConfig.get('courseIDs', list()))})" if oldConfig else ""
        courseIDs = input(
            f"Courses to sync in course ID(split with space){tipStr}:").strip(
            ).split()
        if not courseIDs:
            courseIDs = oldConfig.get('courseIDs', list())
        courseIDs = [int(courseID) for courseID in courseIDs]
        tipStr = f"(Default: {oldConfig.get('downloadDir', '')})" if oldConfig else f"(Default: {os.path.abspath('')})"
        downloadDir = input(f"Path to save canvas files{tipStr}:").strip()
        if not downloadDir:
            downloadDir = os.path.abspath('')
        tipStr = f"(Default: {oldConfig.get('filesizeThresh', '')})" if oldConfig else f"(Default: 250)"
        filesizeThresh = input(
            f"Maximum file size to download(MB){tipStr}:").strip()
        try:
            filesizeThresh = float(filesizeThresh)
        except:
            filesizeThresh = 250
        reDict = {
            "canvasURL": url,
            "token": token,
            "courseCodes": courseCodes,
            "courseIDs": courseIDs,
            "downloadDir": downloadDir,
            "filesizeThresh": filesizeThresh
        }
        with open(CONFIG_PATH, mode='w', encoding='utf-8') as f:
            json.dump(reDict, f, indent=4)
    except Exception as e:
        print(f"\nError: {e.__class__.__name__}. Creating config file fails!")
        exit(1)


def run():
    Syncer = None
    try:
        parser = argparse.ArgumentParser(
            description='A Simple Canvas File Syncer')
        parser.add_argument('-r',
                            help='recreate config file',
                            action="store_true")
        parser.add_argument('-y',
                            help='confirm all prompts',
                            action="store_true")
        parser.add_argument('-p',
                            '--path',
                            help='appoint config file path',
                            default=CONFIG_PATH)
        parser.add_argument('-V',
                            '--version',
                            action='version',
                            version=__version__)
        args = parser.parse_args()
        configPath = args.path
        if args.r or not os.path.exists(configPath):
            if not os.path.exists(configPath):
                print('Config file not exist, creating...')
            initConfig()
            if args.r:
                return
        Syncer = CanvasSyncer(args.y, configPath)
        Syncer.sync()
    except ConnectionError as e:
        print("\nConnection Error! Please check your network and your token!")
        exit(1)
    except Exception as e:
        print(
            f"\nUnexpected Error: {e.__class__.__name__}. Please check your network and your token!"
        )
        raise e
    except KeyboardInterrupt as e:
        if Syncer:
            Syncer.downloader.stop()
        exit(1)


if __name__ == "__main__":
    run()

import os
import re
import json
import requests
from threading import Thread
from queue import Queue
import threading
import time
import argparse
from functools import partial

print = partial(print, flush=True)

CONFIG_PATH = "./.canvassyncer.json"
MAX_DOWNLOAD_COUNT = 16
_sentinel = object()


class MultithreadDownloader:
    def __init__(self, session, maxThread):
        self.sess = session
        self.maxThread = maxThread
        self.countLock = threading.Lock()
        self.taskQueue = Queue()
        self.downloadedCnt = 0
        self.totalCnt = 0

    def downloadFile(self, queue):
        while True:
            src, dst = queue.get()
            if src is _sentinel:
                queue.put([src, dst])
                break
            tryTime = 0
            try:
                while True:
                    try:
                        r = self.sess.get(src, stream=True)
                        break
                    except ConnectionError:
                        tryTime += 1
                        if tryTime == 5:
                            raise Exception("Too many retry!")
                with open(dst + ".tmp", 'wb') as fd:
                    for chunk in r.iter_content(512):
                        fd.write(chunk)
                os.rename(dst + ".tmp", dst)
            except:
                print(f"Error: Download {dst} fails!")
            with self.countLock:
                self.downloadedCnt += 1

    def init(self):
        self.taskQueue = Queue()
        self.downloadedCnt = 0
        self.totalCnt = 0

    def create(self, infos):
        self.init()
        for src, dst in infos:
            self.taskQueue.put((src, dst))
            self.totalCnt += 1
        self.taskQueue.put((_sentinel, _sentinel))

    def start(self):
        for i in range(self.maxThread):
            t = Thread(target=self.downloadFile,
                       args=(self.taskQueue, ),
                       daemon=True)
            t.start()

    @property
    def finished(self):
        return self.downloadedCnt == self.totalCnt

    def waitTillFinish(self):
        while not self.finished:
            print("\r{:5d}/{:5d}  Downloading...".format(
                self.downloadedCnt, self.totalCnt),
                  end='')
            time.sleep(0.1)
        if self.totalCnt > 0:
            print("\r{:5d}/{:5d} Finish!        ".format(
                self.downloadedCnt, self.totalCnt))


class CanvasSyncer:
    def __init__(self, settings_path="./.canvassyncer.json"):
        print(f"\rLoading settings...", end='')
        self.settings = self.loadSettings(settings_path)
        print("\rSettings loaded!    ")
        self.sess = requests.Session()
        self.downloadSize = 0
        self.courseCode = {}
        self.baseurl = self.settings['canvasURL'] + '/api/v1'
        self.downloadDir = self.settings['downloadDir']
        self.downloadFiles = []
        self.laterFiles = []
        self.skipfiles = []
        self.filesLock = threading.Lock()
        self.taskQueue = Queue()
        self.downloader = MultithreadDownloader(self.sess, MAX_DOWNLOAD_COUNT)
        if not os.path.exists(self.downloadDir):
            os.mkdir(self.downloadDir)

    def loadSettings(self, filePath):
        return json.load(open(filePath, 'r', encoding='UTF-8'))

    def sessGet(self, *args, **kwargs):
        try:
            return self.sess.get(*args, **kwargs)
        except:
            raise Exception("Connection error!")

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
            url = f"{self.baseurl}/courses/{courseID}/folders?" + \
                f"access_token={self.settings['token']}&" + \
                f"page={page}"
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
            url = f"{self.baseurl}/courses/{courseID}/files?" + \
                f"access_token={self.settings['token']}&" + \
                f"page={page}"
            files = self.sessGet(url).json()
            if not files:
                break
            for f in files:
                f['display_name'] = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_",
                                           f['display_name'])
                path = f"{folders[f['folder_id']]}/{f['display_name']}"
                path = path.replace('\\', '/').replace('//', '/')
                modifiedTimeStamp = time.mktime(
                    time.strptime(f["modified_at"], "%Y-%m-%dT%H:%M:%SZ"))
                res[path] = (f["url"], int(modifiedTimeStamp))
            page += 1
        return folders, res

    def getCourseCode(self, courseID):
        url = f"{self.baseurl}/courses/{courseID}?" + \
                f"access_token={self.settings['token']}"
        return self.sessGet(url).json()['course_code']

    def getCourseID(self):
        res = {}
        page = 1
        while True:
            url = f"{self.baseurl}/courses?" + \
                    f"access_token={self.settings['token']}&" + \
                    f"page={page}"
            courses = self.sessGet(url).json()
            if not courses:
                break
            for course in courses:
                if course.get('course_code', '').lower() in [
                        s.lower() for s in self.settings['courseCodes']
                ]:
                    res[course['id']] = course['course_code']
            page += 1
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
            if fileName in localFiles:
                localCreatedTimeStamp = int(os.path.getctime(path))
                if fileModifiedTimeStamp <= localCreatedTimeStamp:
                    continue
                self.laterFiles.append((fileUrl, path))
                continue
            response = self.sess.head(fileUrl)
            fileSize = int(response.headers['content-length']) / 2**20
            if fileSize > self.settings['filesizeThresh']:
                isDownload = input(
                    'Target file: %s is too big (%.2fMB), are you sure to download it?(Y/N) '
                    % (fileName, round(fileSize, 2)))
                if isDownload not in ['y', 'Y']:
                    print('Creating empty file as scapegoat')
                    open(path, 'w').close()
                    self.skipfiles.append(path)
                    continue
            self.downloadFiles.append(
                f"{self.courseCode[courseID]}{fileName} ({round(fileSize, 2)}MB)"
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
            print("\rYour local files are already up to date!")
        else:
            print(f"\rFind {len(allInfos)} new files!           ")
            if self.skipfiles:
                print(
                    f"The following file(s) will not be synced due to their size (over {self.settings['filesizeThresh']} MB):"
                )
                [print(f) for f in self.skipfiles]
            print(
                f"Start to download following files! Total size: {round(self.downloadSize, 2)}MB"
            )
            [print(s) for s in self.downloadFiles]
        self.downloader.create(allInfos)
        self.downloader.start()
        self.downloader.waitTillFinish()

    def checkLaterFiles(self):
        if not self.laterFiles:
            return
        print("These files has later version on canvas:")
        [print(path) for (fileUrl, path) in self.laterFiles]
        isDownload = input('Update all?(Y/n)')
        if isDownload in ['n', 'N']:
            return
        for (fileUrl, path) in self.laterFiles:
            localCreatedTimeStamp = int(os.path.getctime(path))
            os.rename(path, f"{path}.{localCreatedTimeStamp}")
        self.downloader.create(self.laterFiles)
        self.downloader.start()
        self.downloader.waitTillFinish()

    def sync(self):
        print("\rGetting course IDs...", end='')
        self.courseCode = self.getCourseID()
        print(f"\rGet {len(self.courseCode)} available courses!")
        self.checkNewFiles()
        self.checkLaterFiles()


def initConfig():
    oldConfig = None
    if os.path.exists(CONFIG_PATH):
        oldConfig = json.load(open(CONFIG_PATH))
    print("Generating new config file...")
    url = input(
        "Please input your canvas url(Default: https://umjicanvas.com):"
    ).strip()
    if not url:
        url = "https://umjicanvas.com"
    tipStr = f"(Default: {oldConfig['token']})" if oldConfig else ""
    token = input(f"Please input your canvas access token{tipStr}:").strip()
    if not token:
        token = oldConfig['token']
    tipStr = f"(Default: {' '.join(oldConfig['courseCodes'])})" if oldConfig else ""
    courses = input(
        f"Please input the code of courses you want to sync(split with space){tipStr}:"
    ).strip().split()
    if not courses:
        courses = oldConfig['courseCodes']
    tipStr = f"(Default: {oldConfig['downloadDir']})" if oldConfig else f"(Default: {os.path.abspath('')})"
    downloadDir = input(
        f"Please input the path you want to save canvas files{tipStr}:").strip(
        )
    if not downloadDir:
        downloadDir = os.path.abspath('')
    tipStr = f"(Default: {oldConfig['filesizeThresh']})" if oldConfig else f"(Default: 250)"
    filesizeThresh = input(
        f"Please input the maximum file size to download in MB{tipStr}:"
    ).strip()
    try:
        filesizeThresh = float(filesizeThresh)
    except:
        filesizeThresh = 250
    reDict = {
        "canvasURL": url,
        "token": token,
        "courseCodes": courses,
        "downloadDir": downloadDir,
        "filesizeThresh": filesizeThresh
    }
    with open(CONFIG_PATH, mode='w', encoding='utf-8') as f:
        json.dump(reDict, f, indent=4)


def run():
    try:
        parser = argparse.ArgumentParser(
            description='A Simple Canvas File Syncer')
        parser.add_argument('-r',
                            help='Recreate config file',
                            action="store_true")
        args = parser.parse_args()
        if args.r or not os.path.exists(CONFIG_PATH):
            initConfig()
        Syncer = CanvasSyncer(CONFIG_PATH)
        Syncer.sync()
    except Exception:
        print("Connection error! Task abort! Please check your network or your token!")


if __name__ == "__main__":
    run()

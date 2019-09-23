import os
import json
import requests
from threading import Thread
import threading
import time
import argparse

CONFIG_PATH = os.path.join(os.path.expanduser('~'), ".canvassyncer")


class CanvasSyncer:
    def __init__(self, settings_path="./settings.json"):
        print(f"\rLoading settings...", end='')
        self.settings = self.load_settings(settings_path)
        print("\rSettings loaded!    ")
        self.sess = requests.Session()
        self.downloaded_cnt = 0
        self.total_cnt = 0
        self.download_size = 0
        self.courseCode = {}
        self.baseurl = self.settings['canvasURL'] + '/api/v1'
        self.download_dir = self.settings['downloadDir']
        self.files = [None]
        self.skipfiles = []
        self.fileslock = threading.Lock()

        if not os.path.exists(self.download_dir):
            os.mkdir(self.download_dir)
        self.local_only_files = []

    def load_settings(self, file_name):
        file_path = os.path.join(
            os.path.split(os.path.realpath(__file__))[0], file_name)
        return json.load(open(file_path, 'r', encoding='UTF-8'))

    def createFolders(self, courseID, folders):
        for folder in folders.values():
            path = os.path.join(self.download_dir,
                                f"{self.courseCode[courseID]}{folder}")
            if not os.path.exists(path):
                os.makedirs(path)

    def getLocalFiles(self, courseID, folders):
        local_files = []
        for folder in folders.values():
            path = os.path.join(self.download_dir,
                                f"{self.courseCode[courseID]}{folder}")
            local_files += [
                os.path.join(folder, f) for f in os.listdir(path)
                if not os.path.isdir(os.path.join(path, f))
            ]
        return local_files

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
            folders = self.sess.get(url).json()
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
            files = self.sess.get(url).json()
            if not files:
                break
            for f in files:
                path = f"{folders[f['folder_id']]}/{f['display_name']}"
                res[path] = f["url"]
            page += 1
        return folders, res

    def downloadFile(self, src, dst):
        r = self.sess.get(src, stream=True)
        with self.fileslock:
            self.files.append(dst)
        with open(dst, 'wb') as fd:
            for chunk in r.iter_content(512):
                fd.write(chunk)
        with self.fileslock:
            self.files.remove(dst)
            self.downloaded_cnt += 1

    def getCourseCode(self, courseID):
        url = f"{self.baseurl}/courses/{courseID}?" + \
                f"access_token={self.settings['token']}"
        return self.sess.get(url).json()['course_code']

    def getCourseID(self):
        res = {}
        page = 1
        while True:
            url = f"{self.baseurl}/courses?" + \
                    f"access_token={self.settings['token']}&" + \
                    f"page={page}"
            courses = self.sess.get(url).json()
            if not courses:
                break
            for course in courses:
                if course.get('course_code') in self.settings['courseCodes']:
                    res[course['id']] = course['course_code']
            page += 1
        return res

    def syncFiles(self, courseID):
        folders, files = self.getCourseFiles(courseID)
        self.createFolders(courseID, folders)
        local_files = [
            f.replace('\\', '/').replace('//', '/')
            for f in self.getLocalFiles(courseID, folders)
        ]
        path = os.path.join(self.download_dir, f"{self.courseCode[courseID]}")
        for fileName, fileUrl in files.items():
            if fileName.replace('\\', '/').replace('//', '/') in local_files:
                local_files.remove(
                    fileName.replace('\\', '/').replace('//', '/'))
            path = os.path.join(self.download_dir,
                                f"{self.courseCode[courseID]}{fileName}")
            if os.path.exists(path):
                continue
            response = self.sess.head(fileUrl)
            fileSize = int(response.headers['content-length']) >> 20
            if fileSize > self.settings['filesizeThresh']:
                # isDownload = input(
                #     'Target file: %s is too big (%.2fMB), are you sure to download it?(Y/N) '
                #     % (fileName, round(fileSize, 2)))
                isDownload = 'N'
                if isDownload not in ['y', 'Y']:
                    # print('Creating empty file as scapegoat')
                    # open(path, 'w').close()
                    self.skipfiles.append(path)
                    continue
            self.download_size += fileSize
            # print(
            #     f"{self.courseCode[courseID]}{fileName} ({round(fileSize, 2)}MB)"
            # )
            Thread(target=self.downloadFile, args=(fileUrl, path),
                   daemon=True).start()
            self.total_cnt += 1
        for f in local_files:
            self.local_only_files.append(f'  {self.courseCode[courseID]}' + f)

    def syncAllCourses(self):
        sync_threads = []
        for course_id in self.courseCode.keys():
            t = Thread(target=self.syncFiles, args=(course_id, ), daemon=True)
            t.start()
            sync_threads.append(t)
        [t.join() for t in sync_threads]
        if self.skipfiles:
            print(
                f"The following file(s) will not be synced due to their size (over {self.settings['filesizeThresh']} MB):"
            )
            [print(f) for f in self.skipfiles]

    def sync(self):
        print("\rGetting course IDs...", end='')
        self.courseCode = self.getCourseID()
        print(f"\rGet {len(self.courseCode)} available courses!")
        print("\rFinding files on canvas...", end='')
        self.syncAllCourses()
        if self.total_cnt == 0:
            print("\rYour local files are already up to date!")
        else:
            print(f"\rFind {self.total_cnt} new files!           ")
            print(f"Start to download! Size: {round(self.download_size, 2)}MB")
            word = 'None'
            while self.downloaded_cnt < self.total_cnt:
                if word not in (str(self.files[-1]) + ' ' * 10) * 2:
                    word = str(self.files[-1]) + ' ' * 10
                print("\r{:5d}/{:5d}  Downloading... {}".format(
                    self.downloaded_cnt, self.total_cnt, word[:15]),
                      end='')
                word = word[1:] + word[0]
                time.sleep(0.1)
            print("\r{:5d}/{:5d} Finish!{}".format(self.downloaded_cnt,
                                                   self.total_cnt, ' ' * 25))
        if self.local_only_files:
            print("\nThese files only exists locally:")
            [print("  " + f) for f in self.local_only_files]


def initConfig():
    print("Generating new config file...")
    url = input(
        "Please input your canvas url(Default: https://umjicanvas.com):"
    ).strip()
    if not url:
        url = "https://umjicanvas.com"
    token = input("Please input your canvas access token:").strip()
    courses = input(
        "Please input the code of courses you want to sync(split with space):"
    ).strip().split()
    downloadDir = input(
        "Please input the path you want to download canvas files:").strip()
    reDict = {
        "canvasURL": url,
        "token": token,
        "courseCodes": courses,
        "downloadDir": downloadDir,
        "filesizeThresh": 150
    }
    with open(CONFIG_PATH, mode='w', encoding='utf-8') as f:
        json.dump(reDict, f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='A Simple Canvas File Syncer')
    parser.add_argument('-r', help='Recreate config file', action="store_true")
    args = parser.parse_args()
    if args.r or not os.path.exists(CONFIG_PATH):
        initConfig()
    Syncer = CanvasSyncer(CONFIG_PATH)
    Syncer.sync()

import os
import json
import requests
from threading import Thread
import time


class CanvasSyncer:
    def __init__(self, settings_path="./settings.json"):
        self.sess = requests.Session()
        self.downloaded_cnt = 0
        self.total_cnt = 0
        self.download_size = 0
        self.courseCode = {}
        print(f"Reading settings from {settings_path} ...")
        self.settings = self.load_settings(settings_path)
        self.baseurl = self.settings['canvasURL'] + '/api/v1'
        self.download_dir = self.settings['downloadDir']
        self.filesize_thresh = self.settings['filesizeThresh']

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
            local_files += [os.path.join(folder, f) for f in os.listdir(path) if not os.path.isdir(os.path.join(path, f))]
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
        with open(dst, 'wb') as fd:
            for chunk in r.iter_content(512):
                fd.write(chunk)
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
        local_files = [f.replace('\\', '/').replace('//', '/') for f in self.getLocalFiles(courseID, folders)]
        path = os.path.join(self.download_dir,
                            f"{self.courseCode[courseID]}")
        for fileName, fileUrl in files.items():
            if fileName.replace('\\', '/').replace('//', '/') in local_files:
                local_files.remove(fileName.replace('\\', '/').replace('//', '/'))
            path = os.path.join(self.download_dir,
                                f"{self.courseCode[courseID]}{fileName}")
            if os.path.exists(path):
                continue
            response = requests.head(fileUrl)
            fileSize = int(response.headers['content-length']) >> 20
            if fileSize > self.filesize_thresh:
                isDownload = input('Target file: %s is too big (%.1fMB), are you sure to download it?(Y/N) ' % (fileName, round(fileSize, 1)))
                if isDownload != 'y' and isDownload != 'Y':
                    print('Creating empty file as scapegoat')
                    open(path, 'w').close()
                    continue
            self.download_size += fileSize
            print(f"{self.courseCode[courseID]}{fileName} ({round(fileSize, 2)}MB)")
            Thread(target=self.downloadFile, args=(fileUrl, path),
                   daemon=True).start()
            self.total_cnt += 1
        for f in local_files:
            self.local_only_files.append(f'  {self.courseCode[courseID]}'+f)
        
    def _sync_all_courses(self):
        sync_threads = []
        for course_id in self.courseCode.keys():
            t = Thread(target=self.syncFiles, args=(course_id,), daemon=True)
            t.start()
            sync_threads.append(t)
        for t in sync_threads:
            t.join()

    def sync(self):
        print("Getting course IDs...")
        self.courseCode = self.getCourseID()
        print(f"Get {len(self.courseCode)} available courses!")
        print("Finding files on canvas...\n")
        self._sync_all_courses()
        print(f"\nFind {self.total_cnt} new files!")
        if not self.total_cnt:
            print("Your local files are already up to date!")
        else:
            print("\nStart to download! \nDownload Size: %.1fMB" %(round(self.download_size, 1)))
            while self.downloaded_cnt < self.total_cnt:
                print("\r{:5d}/{:5d}  Downloading...".format(
                    self.downloaded_cnt, self.total_cnt),
                    end='')
                time.sleep(0.1)
            print("\r{:5d}/{:5d} Finish!        ".format(self.downloaded_cnt,
                                                        self.total_cnt))
        print("\nThese files only exists locally:")
        for f in self.local_only_files:
            print("  " + f)


if __name__ == "__main__":
    Syncer = CanvasSyncer()
    Syncer.sync()

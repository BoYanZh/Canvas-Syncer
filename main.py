import os
import json
import requests
from threading import Thread

class CanvasFileSyncer:
    def __init__(self):
        self.s = requests.Session()
        self.state = 0
        self.totalCount = 0
        self.courseCode = {}

    def load_json(self, file_name):
        file_path = os.path.join(
            os.path.split(os.path.realpath(__file__))[0], file_name)
        try:
            return json.load(open(file_path, 'r', encoding='UTF-8'))
        except:
            print(f"load {file_name} failed")
            return None


    def createFolders(self, courseID, folders):
        for folder in folders.values():
            path = f"./{self.courseCode[courseID]}{folder}"
            if not os.path.exists(path):
                os.makedirs(path)


    def getCourseFolders(self, courseID):
        return [folder for folder in self.getCourseFoldersWithID(courseID).values()]


    def getCourseFoldersWithID(self, courseID):
        res = {}
        page = 1
        while True:
            url = f"{BASEURL}/courses/{courseID}/folders?" + \
                f"access_token={settings['token']}&" + \
                f"page={page}"
            folders = self.s.get(url).json()
            if not folders:
                break
            for folder in folders:
                res[folder['id']] = folder['full_name'].replace("course files", "")
                if not res[folder['id']]:
                    res[folder['id']] = '/'
            page += 1
        return res


    def getCourseFiles(self, courseID):
        folders, res = self.getCourseFoldersWithID(courseID), {}
        page = 1
        while True:
            url = f"{BASEURL}/courses/{courseID}/files?" + \
                f"access_token={settings['token']}&" + \
                f"page={page}"
            files = self.s.get(url).json()
            if not files:
                break
            for f in files:
                path = f"{folders[f['folder_id']]}/{f['display_name']}"
                res[path] = f["url"]
            page += 1
        return folders, res


    def downloadFile(self, src, dst):
        r = self.s.get(src, stream=True)
        with open(dst, 'wb') as fd:
            for chunk in r.iter_content(512):
                fd.write(chunk)
        self.state += 1


    def getCourseCode(self, courseID):
        url = f"{BASEURL}/courses/{courseID}?" + \
                f"access_token={settings['token']}"
        return self.s.get(url).json()['course_code']

    def getCourseID(self):
        page = 1
        while True:
            url = f"{BASEURL}/courses?" + \
                    f"access_token={settings['token']}&" + \
                    f"page={page}"
            courses = self.s.get(url).json()
            if not courses:
                break
            for course in courses:
                if course.get('course_code') in settings['courseCodes']:
                    self.courseCode[course['id']] = course['course_code']
            page += 1

    def syncFiles(self, courseID):
        # courseCode[courseID] = getCourseCode(courseID)
        folders, files = self.getCourseFiles(courseID)
        self.createFolders(courseID, folders)
        for fileName, fileUrl in files.items():
            path = f"./{self.courseCode[courseID]}{fileName}"
            if os.path.exists(path):
                continue
            Thread(target=self.downloadFile, args=(fileUrl, path), daemon=True).start()
            self.totalCount += 1

if __name__ == "__main__":
    syncer = CanvasFileSyncer()
    settings = syncer.load_json("./settings.json")
    BASEURL = settings['canvasURL']
    syncer.getCourseID()
    for courseID in syncer.courseCode.keys():
        syncer.syncFiles(courseID)
    print("Found {} new files! Start to download".format(syncer.totalCount))
    while syncer.state != syncer.totalCount:
        try:
            print("\r{:5d}/{:5d}  Downloading...".format(syncer.state, syncer.totalCount),
                  end='')
        except KeyboardInterrupt:
            break
    print("\r{:5d}/{:5d} Finish!        ".format(syncer.state, syncer.totalCount))

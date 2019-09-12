import os
import json
import requests
from pprint import pprint
from threading import Thread


def load_json(file_name):
    file_path = os.path.join(
        os.path.split(os.path.realpath(__file__))[0], file_name)
    try:
        return json.load(open(file_path, 'r', encoding='UTF-8'))
    except:
        print(f"load {file_name} failed")
        return None


def createFolders(courseID, folders):
    for folder in folders.values():
        path = f"./{courseCode[courseID]}{folder}"
        if not os.path.exists(path):
            os.makedirs(path)


def getCourseFolders(courseID):
    return [folder for folder in getCourseFoldersWithID(courseID).values()]


def getCourseFoldersWithID(courseID):
    res = {}
    page = 1
    while True:
        url = f"{BASEURL}/courses/{courseID}/folders?" + \
              f"access_token={settings['token']}&" + \
              f"page={page}"
        folders = s.get(url).json()
        if not folders:
            break
        for folder in folders:
            res[folder['id']] = folder['full_name'].replace("course files", "")
            if not res[folder['id']]:
                res[folder['id']] = '/'
        page += 1
    return res


def getCourseFiles(courseID):
    folders, res = getCourseFoldersWithID(courseID), {}
    page = 1
    while True:
        url = f"{BASEURL}/courses/{courseID}/files?" + \
              f"access_token={settings['token']}&" + \
              f"page={page}"
        files = s.get(url).json()
        if not files:
            break
        for f in files:
            path = f"{folders[f['folder_id']]}/{f['display_name']}"
            res[path] = f["url"]
        page += 1
    return folders, res


def downloadFile(src, dst):
    global state
    r = s.get(src, stream=True)
    with open(dst, 'wb') as fd:
        for chunk in r.iter_content(512):
            fd.write(chunk)
    state += 1


def getCourseCode(courseID):
    url = f"{BASEURL}/courses/{courseID}?" + \
            f"access_token={settings['token']}"
    return s.get(url).json()['course_code']


def syncFiles(courseID):
    global totalCount
    courseCode[courseID] = getCourseCode(courseID)
    folders, files = getCourseFiles(courseID)
    createFolders(courseID, folders)
    for fileName, fileUrl in files.items():
        path = f"./{courseCode[courseID]}{fileName}"
        if os.path.exists(path):
            continue
        Thread(target=downloadFile, args=(fileUrl, path), daemon=True).start()
        totalCount += 1


s = requests.Session()
state = 0
totalCount = 0
courseCode = {}
BASEURL = "https://umjicanvas.com/api/v1"

if __name__ == "__main__":
    settings = load_json("./settings.json")
    for courseID in settings['courseID']:
        syncFiles(courseID)
    while state != totalCount:
        try:
            print("\r{:5d}/{:5d}  Downloading...".format(state, totalCount),
                  end='')
        except KeyboardInterrupt:
            break
    print("\r{:5d}/{:5d} Finish!        ".format(state, totalCount))
import os
import json
import requests
from pprint import pprint


def load_json(file_name):
    file_path = os.path.join(
        os.path.split(os.path.realpath(__file__))[0], file_name)
    try:
        return json.load(open(file_path, 'r', encoding='UTF-8'))
    except:
        print(f"load {file_name} failed")
        return None


def createFolders(courseID):
    folderList = getCourseFolders(courseID)
    for folder in folderList:
        path = f"./{courseID}{folder}"
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
    return res


s = requests.Session()
BASEURL = "https://umjicanvas.com/api/v1"

if __name__ == "__main__":
    settings = load_json("./settings.json")
    for courseID in settings['courseID']:
        # createFolders(courseID)
        files = getCourseFiles(courseID)
        print(files)
        break
        for fileName in files:
            pass
            # path = f"./{courseID}{folder}"
            # with open(fileName, 'wb') as fd:
            #     for chunk in r.iter_content(512):
            #         fd.write(chunk)
            # break
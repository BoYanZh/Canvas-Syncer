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


def getRootFolders(courseID):
    res = []
    url = f"{BASEURL}/courses/{courseID}/folders?access_token={settings['token']}"
    reList = s.get(url).json()
    for item in reList:
        if item['name'] != 'course files' and item['full_name'].count("/") <= 1:
            res.append({'id': item['id'], 'name': item['name']})
    return res


def getFolders(folderID):
    res = []
    url = f"{BASEURL}/folders/{folderID}/folders?access_token={settings['token']}"
    reList = s.get(url).json()
    for item in reList:
        if item['name'] != 'course files' and item['full_name'].count("/") <= 1:
            res.append({'id': item['id'], 'name': item['name']})
    return res

def getFiles(folderID):
    res = []
    url = f"{BASEURL}/folders/{folderID}/files?access_token={settings['token']}"
    reList = s.get(url).json()
    for item in reList:
        res.append({'id': item['id'], 'name': item['filename']})
    return res

def getFolderTree(courseID):
    res = {}
    rootFolders = getRootFolders(courseID)
    res['folders'] = {folder['name']: {} for folder in rootFolders}
    for folder in rootFolders:
        resFolders = getFolders(folder['id'])
        res['folders'][folder['name']]['folders'] = {folder['name']: {} for folder in resFolders}
    return res

def getSubFolders(folderID):
    res = {}
    resFolders = getFolders(folderID)
    for folder in resFolders:
        res['folder'] = folder['name']
    return res

s = requests.Session()
BASEURL = "https://umjicanvas.com/api/v1"

if __name__ == "__main__":
    settings = load_json("./settings.json")
    pprint(getFolderTree(settings['courseID'][0]))
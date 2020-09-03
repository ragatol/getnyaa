#!/usr/bin/python3
#
#########################################################################
# nyaa.si auto downloader
# -----------------------
#
# Automatically checks for new episodes from a nyaa.si user RSS,
# adding the download to transmission-daemon and moving to the
# anime library once completed. Does the cleanup of finished
# torrents too.
#
# 2020 Rafael Fernandes - Public Domain
#

import xml.etree.ElementTree as XML
import json
import subprocess
import re
import os
from pathlib import Path

#
# Config file and utilities
#

print("Starting getnyaa:")

global CONFIG
with open("config.json") as f:
    CONFIG = json.load(f)

def episodeFolder(anime_name,season):
    return f'{CONFIG["library_dir"]}/{anime_name}/Season {season:02}/'

def episodeFilename(anime_name,season,episode):
    return f'{anime_name} - S{season:02}E{episode:02}'

def getTransmissionLogin():
    return f'{CONFIG["user"]}:{CONFIG["password"]}'

def runTransmission(args,capture=False):
    targs = ['transmission-remote','-n',getTransmissionLogin()] + args
    return subprocess.run(targs,capture_output=capture,text=True)

def getOrganizeFilename(torrent_hash):
    return f'{CONFIG["download_dir"]}/{torrent_hash}.getnyaa'

# 
# Check for missing episodes from Nyaa.si RSS feeds
# and add them to transmission
#

def addEpisodeTorrent(url):
    runTransmission(['-a',url])

def isMissingEpisode(season_folder,filename):
    folder = Path(season_folder)
    if (not folder.exists()):
        return True
    for f in folder.iterdir():
        if (str.upper(f.stem) == str.upper(filename)):
            return False
    return True

def addOrganizeFile(thash,target_folder,target_name):
    org_filename = getOrganizeFilename(thash)
    print("Adding organize file",org_filename)
    org_info = {
        "season_dir": target_folder,
        "episode": target_name
    }
    with Path(org_filename) as p:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(org_info))

def isWantedEpisode(title, url, thash, anime_list):
    for anime in anime_list:
        if not re.search(anime["search_re"],title):
            continue # test next anime in anime_list
        print(f'Found match for {title}')
        try:
            item_episode = int(re.search(anime["episode_re"],title).group(1))
        except:
            print("Could not find episode number from torrent title, check 'episode_re' on config.json")
            return
        season_folder = episodeFolder(anime["name"],anime["season"])
        episode_file = episodeFilename(anime["name"],anime["season"],item_episode)
        print("Checking if",episode_file,"is missing...")
        if (isMissingEpisode(season_folder,episode_file)):
            print(episode_file,"missing, adding torrent to transmission.")
            addEpisodeTorrent(url)
            addOrganizeFile(thash,season_folder,episode_file)
        else:
            print(episode_file,"already in library, skipping.")
        return # go to next item in RSS

def findEpisodes(user,anime_list):
    from urllib.request import urlopen
    ns = { "nyaa" : "https://nyaa.si/xmlns/nyaa" } 
    try:
        rss = urlopen(f"https://nyaa.si/?page=rss&user={user}")
        src_rss = XML.fromstring(rss.read())
    except:
        print("Could not load",user,"RSS!")
        return
    for item in src_rss.findall("channel/item"):
        title =  item.find("title").text
        url = item.find("link").text
        thash = item.find("nyaa:infoHash",ns).text
        isWantedEpisode(title,url,thash,anime_list)

def checkNewEpisodes(src_list):
    for src in src_list:
        print("Processing",src["user"])
        findEpisodes(src["user"],src["animes"])

print("\nChecking for new episodes:")
checkNewEpisodes(CONFIG["sources"])

#
# Check if download finished, and copy to destination anime folder
#

def removedTorrent(thash):
    r = runTransmission(['-t',thash])
    return r.returncode != 0

def getDownloadStatus(thash):
    r = runTransmission(['-t',thash,'-i'],capture=True)
    downloaded = False
    finished = False
    for l in r.stdout.splitlines():
        match = re.search("State: (\\w+)",l)
        if (match and match.group(1) == "Finished"):
            finished = True
        match = re.search('Percent Done: (.*)%',l)
        if (match and match.group(1) == "100"):
            downloaded = True
    return (downloaded,finished)

def getDownloadFilename(thash):
    r = runTransmission(['-t',thash,'-f'],capture=True)
    lines = r.stdout.splitlines()
    t_header = lines[1]
    t_file = lines[2]
    m = re.search("Name",t_header)
    f_start = m.span()[0]
    filename = t_file[f_start:]
    return filename

def copyToLibrary(thash,info):
    from shutil import copyfile
    src_path = Path(CONFIG["download_dir"]) / getDownloadFilename(thash)
    dst_file = info["episode"] + src_path.suffix
    dst_path = Path(info["season_dir"]) / dst_file
    if (dst_path.exists()): return # dont overwrite existing file
    print("Copying new episode",src_path,"to",dst_path,"...")
    dst_path.parent.mkdir(parents=True,exist_ok=True)
    copyfile(src_path,dst_path)

def cleanTorrent(thash,info):
    print("Cleaning torrent of",info["episode"],"...")
    runTransmission(['-t',thash,'--remove-and-delete'])

def checkDownloads():
    for f in Path(CONFIG["download_dir"]).glob("*.getnyaa"):
        thash = f.stem
        info = json.loads(f.read_text())
        print("Checking torrent",thash,"of episode",info["episode"],"...")
        if (removedTorrent(thash)):
            f.unlink()
            continue
        (downloaded,finished) = getDownloadStatus(thash)
        if (downloaded):
            copyToLibrary(thash,info)
        if (finished):
            cleanTorrent(thash,info)
            f.unlink()

print("\nChecking downloads:")
checkDownloads()

#!/usr/bin/env python3

#########################################################################
# nyaa.si auto downloader
# -----------------------
#
# Automatically checks for new episodes from a nyaa.si user RSS,
# adding the download to transmission-daemon and moving to the
# anime library once completed. Does the cleanup of finished
# torrents too.
#
# 2020-2022 Rafael Fernandes - Public Domain
#
#########################################################################


import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as XML


#
# Config file and utilities
#


global CONFIG
global TRANSMISSION_LOGIN
global LIBRARY_DIR
global COPY_CMD
with open("config.json") as f:
    CONFIG = json.load(f)
    TRANSMISSION_LOGIN = f'{CONFIG["user"]}:{CONFIG["password"]}'
    LIBRARY_DIR = CONFIG["library_dir"]
    COPY_CMD = CONFIG.get("copy_cmd", "cp")


def has_episode(episode_path):
    anime_path = episode_path.parent
    if (not anime_path.exists()):
        return False
    for f in anime_path.glob(episode_path.name + ".*"):
        return f.stem == episode_path.name
    return False


def transmission_cmd(args, capture=False):
    targs = ['transmission-remote', '-n', TRANSMISSION_LOGIN] + args
    return subprocess.run(targs, capture_output=True, text=True)


def get_organize_filename(torrent_hash):
    return f'{CONFIG["download_dir"]}/{torrent_hash}.getnyaa'


# Functions for checking for new episodes in a Nyaa.si RSS
# and adding them to transmission


def add_torrent(url):
    transmission_cmd(['-a', url])


def add_organize_file(thash, destination):
    org_filename = get_organize_filename(thash)
    print("Adding organize file", org_filename)
    p = Path(org_filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(destination))


def overall_episode_str(name, episode, start_offset=None):
    if start_offset is not None:
        episode = episode - 1 + start_offset
    return f"{name} - {episode:02}"


def seasonal_episode_str(name, episode, season, cour=None, start=None, end=None):
    if cour is not None and start is not None:
        # can't have both cour and seasonal conversion
        print("Both season_continue and season_start are set, this is an error.")
        return None
    if cour is not None:
        # continue season from cour (season_continue) episode
        episode = episode - 1 + cour
    if start is not None:
        # convert overral numbering to seasonal numbering
        episode = episode - start + 1
        if (episode <= 0) or ((end is not None) and (episode > end)):
            # episode is not of this season
            print(f"Episode not of this season: {season:02}.")
            return None
    return f"Season {season:02}/{name} - S{season:02}E{episode:02}"


def make_episode_filename(anime, episode):
    name = anime["name"]
    season = anime.get("season", 0)
    cour = anime.get("season_continue")
    start = anime.get("season_start")
    end = anime.get("season_end")
    if season == 0:
        # use overall numbering of episodes
        return overall_episode_str(name, episode, start)
    else:
        # use seasonal numbering of episodes
        return seasonal_episode_str(name, episode, season, cour, start, end)


def check_episode(title, url, thash, anime_list):
    for anime in anime_list:
        match = re.search(anime["search_re"], title, re.IGNORECASE)
        if not match:
            continue  # test next anime in anime_list
        print(f'Found match for {title}')
        try:
            episode = int(match.group(1))
        except:
            print("Could not find episode number from torrent title, check 'search_re' on config.json")
            return
        anime_name = anime["name"]
        ep_filename = make_episode_filename(anime, episode)
        if ep_filename is None:
            continue
        episode_path = Path(f'{LIBRARY_DIR}/{anime_name}/{ep_filename}')
        print("Checking if", episode_path.name, "is missing...")
        if (not has_episode(episode_path)):
            print(episode_path.name, "missing, adding torrent to transmission.")
            add_torrent(url)
            add_organize_file(thash, episode_path)
        else:
            print(episode_path.name, "already in library, skipping.")
        return  # go to next item in RSS


def check_rss_episodes(user, anime_list):
    from urllib.request import urlopen
    ns = {"nyaa": "https://nyaa.si/xmlns/nyaa"}
    try:
        rss = urlopen(f"https://nyaa.si/?page=rss&user={user}")
        src_rss = XML.fromstring(rss.read())
    except:
        print("Could not load", user, "RSS!")
        return
    for item in src_rss.findall("channel/item"):
        title = item.find("title").text
        url = item.find("link").text
        thash = item.find("nyaa:infoHash", ns).text
        check_episode(title, url, thash, anime_list)


def search_new_episodes(src_list):
    for src in src_list:
        print("\nProcessing", src["user"])
        check_rss_episodes(src["user"], src["animes"])


# Functions for checking download progress and
# organizing downloaded episodes


def is_torrent_removed(thash):
    r = transmission_cmd(['-t', thash])
    return r.returncode != 0


def get_download_status(thash):
    r = transmission_cmd(['-t', thash, '-i'], capture=True)
    downloaded = False
    finished = False
    for line in r.stdout.splitlines():
        match = re.search(r'State: (\w+)', line)
        if (match and match.group(1) == "Finished"):
            finished = True
        match = re.search('Percent Done: (.*)%', line)
        if (match and match.group(1) == "100"):
            downloaded = True
    return (downloaded, finished)


def get_download_filename(thash):
    r = transmission_cmd(['-t', thash, '-f'], capture=True)
    lines = r.stdout.splitlines()
    t_header = lines[1]
    t_file = lines[2]
    m = re.search("Name", t_header)
    f_start = m.span()[0]
    filename = t_file[f_start:]
    return filename


def copy_to_library(thash, dst_path):
    src_file = Path(CONFIG["download_dir"]) / get_download_filename(thash)
    dst_file = Path(str(dst_path) + src_file.suffix)
    if (dst_file.exists()):
        return  # dont overwrite existing file
    print("Copying new episode", src_file, "to", dst_file, "...")
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    copy_cmd_args = [COPY_CMD, str(src_file), str(dst_file)]
    r = subprocess.run(copy_cmd_args)
    if r.returncode != 0:
        print("Error while copying: ", copy_cmd_args)


def clean_torrent(thash, path):
    print("Cleaning torrent of", path.name, "...")
    transmission_cmd(['-t', thash, '--remove-and-delete'])


def check_downloads():
    for f in Path(CONFIG["download_dir"]).glob("*.getnyaa"):
        thash = f.stem
        dst_path = Path(f.read_text())
        print("Checking torrent", thash, "of episode", dst_path.name, "...")
        if (is_torrent_removed(thash)):
            f.unlink()
            continue
        (downloaded, finished) = get_download_status(thash)
        if (downloaded):
            copy_to_library(thash, dst_path)
        if (finished):
            clean_torrent(thash, dst_path)
            f.unlink()


if __name__ == "__main__":
    # Allow only 1 instance running
    lockfile = Path("/tmp/getnyaa")
    if lockfile.exists():
        quit(0)
    lockfile.touch()
    print("Searching for new episodes:")
    search_new_episodes(CONFIG["sources"])
    print("\nChecking downloads:")
    check_downloads()
    lockfile.unlink()

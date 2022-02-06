# Nyaa.si Auto Downloader #

A simple script to automate checking for new episodes of animes from your
preferred uploaders at nyaa.si, adding them to transmission-daemon, and
managing completed downloads.

Requires transmission-daemon and transmission-remote, Python 3.5+, and some
understanding of json and regular expressions.

Add it to your crontab or similar service to run automatically.

Note that the script looks for config.json at the current working directory, so
change to the directory that contains the config.json file before running the
script. For example, if using cron to call the script, do a simple shell script
with the following lines:

~~~shell
#!/bin/sh
cd /path/to/config
/path/to/getnyaa.py
~~~

If your config is in the same directory as the getnyaa script, then just add
this as your command in your crontab:

~~~shell
cd /path/to/getnyaa_dir && ./getnyaa.py
~~~

The script prints to stdout what it is doing for each entry in the RSS that
matches the search rules defined in config.json. To log to a file instead, just
redirect. For example, the previous script could be rewritten to:

~~~shell
#!/bin/sh
cd /path/to/config
/path/to/getnyaa.py > /var/log/getnyaa.log
~~~

For example, to run the script to check for new episodes each hour and log the
output, add this line to your crontab using `crontab -e`:

`0 * * * * cd /path/to/getnyaa && ./getnyaa.py > ~/getnyaa.log`

## How to configure ##

The config.json is structured like this:

- user: your remote transmission-daemon username;
- password: your remote transmission-daemon password;
- download_dir: path where transmision-daemon saves completed torrents;
- library_dir: path to where your library is. It'll be used to check if a
  episode already exists, and to copy new episodes.
- sources: list of uploaders from nyaa.si;

The script needs to be able to write to both __download_dir__ and
__library_dir__.

"sources" is a list of objects with the following keys:

- user: username of the uploader, the last part of the user url, e.g.: if the
  uploader list of torrents is in `https://nyaa.si/user/sff`, the the user is
  "sff".
- animes: list of objects that have configuration on how to search and organize
  the anime.

"animes" is a list of objects with the following keys:

- name: The name of the anime. It'll be used as the directory name inside your
  "library_dir";
- episode_re: A regular expression that is matched against the torrent name.
  Must have a capture group of the episode number;
- season (optional): The season number. See EPISODE ORGANIZATION for details;
- season_start (optional): See EPISODE ORGANIZATION for details;
- seaosn_end (optional): See EPISODE ORGANIZATION for details;

See the included "config.json" as an example.

## Writing an __epsiode_re__ expression ##

A simple way to create a __epsiode_re__ expression is to visit the torrent
description, copying the torrent title, and doing the following edits:

- Delete tags like `[HEVC]`, and anything thad doesn't contribute to identify
  the particular anime episode.
- If there's both overall and seasonal episode numbers, delete one of them.
  Leave the text right before the episode number so it can be used to identify
  where the episode number is.
- Replace other text between the anime name and the episode number with `.*`.
- Replace the episode number with (\\\\d+). If you are interested on the
  overral episode number, change the "Ep. 33" with "Ep. (\\\\d+)". If you are
  interested in seasonal episode number, change the "S02E01" with
  "S02E(\\\\d+)". Note that the `\d` regular expression uses `\`, which needs to
  be escaped in a json string, using `\\d`.

Example:

Consider the following torrent title:

`[Judas] Shingeki no Kyojin - S04E20 (Attack on Titan) (Ep.79) [1080p][HEVC x265 10bit][Multi-Subs] (Weekly)`

There's both seasonal and overall episode numbers.

For overall numbering, you can use the following __search_re__ :

`Shingeki no Kyojin.*Ep.(\\d+)`

For seasonal numbering, you can use the following __search_re__:

`Shingeki no Kyojin.*S04E(\\d+)`

Check the next section for more complex situations, like converting seasonal
episode numbers to overall episode numbers.

## EPISODE ORGANIZATION ##

Consider __library_dir__ as your library root. For each anime configured in
config.json, a path for seaching and copying episodes is constructed.

In the following examples, note that the filename extension (".mkv") is just an
example, the script doesn't care about it in practice.

### USING OVERALL EPISODE NUMBERING ###

If you prefer that all episodes are placed inside the anime folder, with
episodes numbered from 1 to the last, without separating by seasons, then just
don't use the __season__ key when configuring an anime.

For example, the following anime configuration:

~~~json
{
  "name": "Attack on Titan",
  "search_re": "Shingeki no Kyojin.*Ep..(\\d+)"
}
~~~

Will check for and copy new episodes like this:

`Attack on Titan/Attack on Titan - 33.mkv`

If the uploader only uses seasonal numbering, you can convert it to overall
numbering using __season_start__. For example, the first episode of the fourth
season of Attack on Titan is the 60th episode in overall numbering. Adding
`"season_start": 60` to the configuration, will convert episode 1 of season 4 to
episode 60 overall:

~~~json
{
  "name": "Attack on Titan",
  "search_re": "Shingeki no Kyojin.*S04E(\\d+)",
  "season_start": 60
}
~~~

Will convert S04E01 to `Shingeki no Kyojin - 60.mkv`.

### USING SEASONAL EPISODE NUMBERING ###

If you prefer organized like some media servers do (e.g. Jellyfin), separated
by seasons, use the __season__ key when configuring an anime like this:

~~~json
{
  "name": "Attack on Titan",
  "search_re": "Shinkegi no Kyojin.*S04E(\\d+)",
  "season": 4
}
~~~

Then, the script will check for and add new episodes like this:

`Attack on Titan/Season 04/Attack on Titan - S04E01.mkv`

If the uploader doesn't name the torrent with a seasonal numbering, you can
convert overall numbering to seasonal numbering using __season_start__ and,
optionally, __season_end__. For example, with the following configuration:

~~~json
{
  "name": "Attack on Titan",
  "search_re": "Shingeki no Kyokin.*Ep..(\\d+)",
  "season": 2,
  "season_start": 26
}
~~~

The script will only check for episodes starting episode 26, and will convert
it to:

`Attack on Titan/Season 02/Attack on Titan - S02E01.mkv`

If you add __season_end__:

`"season_end": 37`

Then the script will ignore episodes 38 and forward, as they are not of this
particular season.

#!/usr/bin/env python3
# Alan Witkowski
#
import json
import platform
import urllib
import sys
import time
import curses
import subprocess
import shlex
import os
import html.parser
from urllib.parse import quote
from urllib.request import urlopen

# create cache directory
cache_path = os.path.expanduser("~/.cache/redpi/")
files_path = os.path.expanduser("~/.cache/redpi/files/")
os.makedirs(cache_path, exist_ok=True)
os.makedirs(files_path, exist_ok=True)

mode_results = {
	"downloads" : [],
	"reddit" : [],
	"youtube" : []
}

mode_status = {
	"downloads" : "",
	"reddit" : "type s to select subreddit",
	"youtube" : "type / to search youtube" 
}

mode_help = {
	"downloads" : "1: downloads 2: reddit 3: youtube a: playall d: delete r: refresh q: quit",
	"reddit" : "1: downloads 2: reddit 3: youtube s: subreddit /: search r: refresh q: quit",
	"youtube" : "1: downloads 2: reddit 3: youtube /: search q: quit"
}

if platform.machine()[:3] == "arm":
	play_command = "omxplayer"
else:
	play_command = "vlc -q"

DEVNULL = open(os.devnull, "w")
position = 0
expire_time = 600
max_display = 20
screen = None
downloads = []
menu_status = None
menu_help = None
scroll = 0
mode = 'downloads'
max_y = 0
max_x = 0
html_parser = html.parser.HTMLParser()

def load_youtube(search=""):
	global mode_results

	set_status("searching youtube for \"" + search + "\"")

	# build url
	url = "https://www.googleapis.com/youtube/v3/search?key=AIzaSyDBtXPQRsI7Ny7JZ335nq-4VGLfOk4dSJI&type=video&part=snippet&maxResults=50&q=" + urllib.parse.quote(search)
	
	# get results
	mode_results['youtube'] = []
	request = urllib.request.Request(url)
	try:
		response = urllib.request.urlopen(request)
	except:
		return

	# get json object
	json_str = response.readall().decode("utf-8")
	decoded = json.loads(json_str)

	# get children
	children = decoded['items']

	# build results
	i = 0
	count_width = 2
	date_width = 10
	channel_width = 20
	title_width = max_x - (count_width+1) - (channel_width+1) - (date_width+1) - 0
	template = "{0:%s} {1:%s} {2:%s} {3:%s}" % (count_width, title_width, channel_width, date_width)
	for item in children:
		id = item['id']['videoId']
		title = item['snippet']['title'][:title_width]
		channel = item['snippet']['channelTitle'][:channel_width]
		published_at = item['snippet']['publishedAt']
		tdate = time.strptime(published_at, "%Y-%m-%dT%H:%M:%S.%fZ")

		# build row
		row = [str(i+1), title, channel, time.strftime("%m-%d-%Y", tdate)]

		data = {}
		data['display'] = template.format(*row)
		data['video'] = id
		mode_results['youtube'].append(data)
		i += 1
	
	mode_status['youtube'] = "searched \"" + search + "\""
	set_status(mode_status['youtube'])

def load_subreddit(subreddit, search="", force=0):
	global expired_time, mode_results
	cache_file = cache_path + subreddit + ".json"
	status_string = ""

	# load cached results
	mode_results['reddit'] = []
	decoded = ""
	if subreddit == "":
		url_subreddit = "/"
	else:
		url_subreddit = "/r/" + subreddit

	if search == "":
		set_status("loading /r/" + subreddit)
		if force == 0 and os.path.isfile(cache_file) and time.time() - os.path.getmtime(cache_file) <= expire_time:
			status_string = "/r/" + subreddit + " from cache"
			with open(cache_file, "r") as file_in:
				decoded = json.load(file_in)
		else:
			if subreddit == "":
				status_string = "reddit frontpage"
			else:
				status_string = "/r/" + subreddit
			url = "http://www.reddit.com" + url_subreddit + ".json?limit=90"
	else:
		status_string = "searched \"" + search + "\" in /r/" + subreddit
		url = "http://www.reddit.com" + url_subreddit + "/search.json?limit=90&q=" + urllib.parse.quote(search) + "&restrict_sr=on"
	
	# load live page
	if decoded == "": 
		header = { 'User-Agent' : 'cool json bot' }
		request = urllib.request.Request(url, headers=header)
		try:
			response = urllib.request.urlopen(request)
		except:
			set_status("request failed")
			return

		json_str = response.readall().decode("utf-8")
		decoded = json.loads(json_str)

		# cache json file
		if search == "" and decoded['data']['children']:
			with open(cache_file, "w") as file_out:
				file_out.write(json_str)

	# get children
	children = decoded['data']['children']

	# build results
	i = 0
	count_width = 2
	vote_width = 5
	domain_width = 20
	title_width = max_x - (count_width+1) - (vote_width+1) - (domain_width+1) - 0
	template = "{0:%s} {1:%s} {2:%s} {3:%s}" % (count_width, vote_width, title_width, domain_width)
	for item in children:
		title = html_parser.unescape(item['data']['title'][:title_width].replace('\r\n', ''))
		url = item['data']['url']
		score = str(item['data']['ups'] -  item['data']['downs'])[:vote_width]
		domain = item['data']['domain'][:domain_width]
		media = item['data']['media']

		row = [str(i+1), score, title, domain]
		data = {}
		data['display'] = template.format(*row)
		if media != None and 'oembed' in media and media['oembed']['type'] == "video":
			data['video'] = item['data']['url']
		mode_results['reddit'].append(data)
		i += 1

	mode_status['reddit'] = status_string
	set_status(status_string)

def load_downloads():
	global mode_results

	# build list of downloads
	mode_results['downloads'] = []
	i = 0
	count_width = 2
	date_width = 19
	title_width = max_x - (count_width+1) - (date_width+1)
	template = "{0:%s} {1:%s} {2:%s}" % (count_width, title_width, date_width)
	files = os.listdir(files_path)
	for file in files:
		cdate = time.localtime(os.path.getctime(os.path.join(files_path, file)))
		row = [str(i+1), file[:title_width], time.strftime("%Y-%m-%d %I:%M %p", cdate)]

		data = {}
		data['display'] = template.format(*row)
		data['video'] = file
		mode_results['downloads'].append(data)
		i += 1

	set_status(str(len(downloads)) + " download(s) in progress")

def draw_results():
	global menu_results

	if len(mode_results[mode]) == 0:
		menu_results.addstr(0, 0, "No results")
	else:
		i = 0
		for row in mode_results[mode][scroll : scroll + max_display]:
			color = 1
			if position == i:
				color = 2
			menu_results.addstr(i, 0, row['display'], curses.color_pair(color))
			i += 1
			if i >= max_display:
				break

	menu_results.noutrefresh(0, 0, 1, 0, max_y-2, max_x-1)

def draw_help():
	global menu_help
	menu_help.erase()
	menu_help.addstr(0, 0, mode_help[mode][:max_x-1], curses.A_BOLD)
	menu_help.noutrefresh(0, 0, 0, 0, max_y-1, max_x-1)

def restore_state():
	draw_help()
	draw_results()
	curses.halfdelay(10)

def play_video(file):
	global screen, DEVNULL

	os.chdir(files_path)
	command = play_command + " \"" + file.replace("\"", "\\\"") + "\""
	args = shlex.split(command)
	try:
		screen.clear()
		screen.refresh()

		play_process = subprocess.Popen(args, stdout=DEVNULL, stderr=DEVNULL)
		play_process.wait()
		set_status("finished " + file)

		restore_state()
	except:
		set_status("playback failed")

		restore_state()
		return 1

	return 0

def handle_selection():
	global downloads

	if len(mode_results[mode]) == 0:
		return

	index = position + scroll
	if 'video' in mode_results[mode][index]:
		video = mode_results[mode][index]['video']
		if mode != 'downloads':
			set_status("downloading: " + video)
			os.chdir(files_path)
			command = "youtube-dl -q --restrict-filenames " + video
			args = shlex.split(command)
			process = subprocess.Popen(args)
			downloads.append(process)
			restore_state()
		else:
			return play_video(video)

	return 0

def handle_playall(screen):

	if len(mode_results[mode]) == 0:
		return

	index = position + scroll
	for item in mode_results[mode][index:]:
		if 'video' in item:
			video = item['video']
			status = play_video(video)
			c = screen.getch()
			if c == 27:
				set_status("cancelled playlist")
				return 1

			if status == 1:
				return 1

	return 0

def delete_selection():
	if len(mode_results[mode]) == 0:
		return

	index = position + scroll
	if mode == 'downloads':
		file = os.path.join(files_path, mode_results[mode][index]['video'])
		if os.path.isfile(file):
			os.remove(file)

	set_status("deleted " + file)

	return 0

def set_status(text):
	global menu_status
	menu_status.erase()
	menu_status.addstr(0, 0, text[:max_x], curses.A_BOLD)
	menu_status.noutrefresh(0, 0, max_y-1, 0, max_y-1, max_x-1)
	curses.doupdate()

def get_input(text, screen):
	curses.echo()
	curses.curs_set(1)
	screen.addstr(max_y-2, 0, text)
	input = screen.getstr(max_y-2, len(text), 50).decode('utf-8')
	curses.noecho()
	curses.curs_set(0)

	return input

def main(stdscr):
	global downloads, position, mode, max_x, max_y, scroll, menu_status, menu_results, menu_help, max_display, screen

	subreddit = ""
	search = ""
	screen = curses.initscr()
	curses.curs_set(0)

	(max_y, max_x) = screen.getmaxyx()
	max_display = max_y - 4
	curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
	
	menu_results = curses.newpad(100, 300)
	menu_status = curses.newpad(1, 300)
	menu_help = curses.newpad(1, 300)
	restore_state()

	load_downloads()
	draw_results()
	draw_help()
	curses.doupdate()

	while True:
		c = screen.getch()
		redraw = 0
		if c == curses.KEY_RESIZE:
			(max_y, max_x) = screen.getmaxyx()
			max_display = max_y - 4
			menu_results.clear()
			redraw = 1
		elif c == 10:
			status = handle_selection()
		elif c == ord('1'):
			mode = 'downloads'
			load_downloads()
			menu_results.erase()
			position = 0
			scroll = 0
			redraw = 1
		elif c == ord('2'):
			mode = 'reddit'
			menu_results.erase()
			set_status(mode_status[mode])
			redraw = 1
		elif c == ord('3'):
			mode = 'youtube'
			menu_results.erase()
			set_status(mode_status[mode])
			redraw = 1
		elif c == ord('a'):
			handle_playall(screen)
		elif c == ord('q'):
			break
		elif c == ord('d'):
			if mode == 'downloads':
				delete_selection()
				menu_results.erase()
				load_downloads()
				if scroll + max_display > len(mode_results[mode]):
					scroll = len(mode_results[mode]) - max_display
					if scroll < 0:
						scroll = 0
				if position >= len(mode_results[mode]):
					position -= 1
				redraw = 1
		elif c == ord('/'):
			if mode == 'reddit':

				# get input
				search = get_input("search /r/" + subreddit + ": ", screen)

				# load results
				if search != "":
					position = 0
					scroll = 0
					load_subreddit(subreddit, search)
					menu_results.erase()
					redraw = 1
			elif mode == 'youtube':

				# get input
				query = get_input("youtube: ", screen)

				# load new subreddit
				if query != "":
					position = 0
					scroll = 0
					load_youtube(query)
					menu_results.erase()
					redraw = 1

		elif c == ord('s'):
			if mode == 'reddit':

				# get input
				subreddit = get_input("subreddit: ", screen)

				# load new subreddit
				position = 0
				scroll = 0
				search = ""
				load_subreddit(subreddit)
				menu_results.erase()
				redraw = 1
		elif c == ord('r'):
			if mode == 'reddit':
				position = 0
				scroll = 0
				load_subreddit(subreddit, search, force=1)
				menu_results.erase()
				redraw = 1
			elif mode == 'downloads':
				menu_results.erase()
				load_downloads()
				position = 0
				scroll = 0
				redraw = 1
		elif c == curses.KEY_UP or c == ord('k'):
			if position <= 0 and scroll > 0:
				scroll -= 1
			elif position + scroll > 0:
				position -= 1
			redraw = 1
		elif c == curses.KEY_DOWN or c == ord('j'):
			if position >= max_display-1 and scroll < len(mode_results[mode]) - max_display:
				scroll += 1
			elif position + scroll < len(mode_results[mode]) - 1:
				position += 1
			redraw = 1

		if redraw:
			draw_results()
			draw_help()

		# check for finished downloads
		for download in downloads[:]:
			download.poll()
			if download.returncode != None:
				downloads.remove(download)
				set_status("download finished")

		curses.doupdate()

	curses.endwin()

curses.wrapper(main)

#!/usr/bin/env python3
# Alan Witkowski
#
import json
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
files_path = os.path.expanduser("~/.cache/redpi/files/")
cache_path = os.path.expanduser("~/.cache/redpi/")
os.makedirs(files_path, exist_ok=True)

play_command = "omxplayer"
#play_command = "vlc -q"

position = 0
expire_time = 300
results = []
max_display = 20
process = None
menu_status = None
scroll = 0
mode = 0
max_y = 0
max_x = 0
html_parser = html.parser.HTMLParser()

def load_subreddit(subreddit, search="", force=0):
	global expired_time, results
	cache_file = cache_path + subreddit + ".json"

	# load cached results
	decoded = ""
	if search == "":
		if force == 0 and os.path.isfile(cache_file) and time.time() - os.path.getmtime(cache_file) <= expire_time:
			with open(cache_file, "r") as file_in:
				decoded = json.load(file_in)
		else:
			url = "http://www.reddit.com/r/" + subreddit + ".json?limit=100"
	else:
		url = "http://www.reddit.com/r/" + subreddit + "/search.json?limit=100&q=" + urllib.parse.quote(search) + "&restrict_sr=on"
	
	# load live page
	if decoded == "": 
		header = { 'User-Agent' : 'cool json bot' }
		request = urllib.request.Request(url, headers=header)
		try:
			response = urllib.request.urlopen(request)
		except:
			children = [] 
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
	results = []
	i = 0
	title_width = 46
	template = "{0:2} {1:5} {2:%s} {3:20}" % title_width
	for item in children:
		title = html_parser.unescape(item['data']['title'][:title_width])
		url = item['data']['url']
		score = str(item['data']['ups'] -  item['data']['downs'])
		domain = item['data']['domain'][:20]
		media = item['data']['media']

		row = [str(i+1), score, title, domain]
		data = {}
		data['display'] = template.format(*row)
		if media != None and 'oembed' in media and media['oembed']['type'] == "video":
			data['video'] = item['data']['url']
		results.append(data)
		i += 1

def load_downloads():
	global results

	# build list of downloads
	results = []
	i = 0
	title_width = 70
	template = "{0:2} {1:%s}" % title_width
	files = os.listdir(files_path)
	for file in files:
		row = [str(i+1), file[:title_width]]

		data = {}
		data['display'] = template.format(*row)
		data['video'] = file
		results.append(data)
		i += 1

def draw_results(menu):

	if len(results) == 0:
		menu.addstr(0, 0, "No results")
	else:
		i = 0
		for row in results[scroll : scroll + max_display]:
			color = 1
			if position == i:
				color = 2
			menu.addstr(i, 0, row['display'], curses.color_pair(color))
			i += 1
			if i >= max_display:
				break

	menu.noutrefresh(0, 0, 1, 0, max_y-2, max_x-1)

def draw_help(menu):
	menu.clear()
	if mode == 0:
		menu.addstr(0, 0, "r: refresh, s: subreddit, l: downloads, j: up, k: down, enter: download", curses.A_BOLD)
	elif mode == 1:
		menu.addstr(0, 0, "r: refresh, s: subreddit, l: results, d: delete, j: up, k: down, enter: play", curses.A_BOLD)
	menu.noutrefresh(0, 0, 0, 0, max_y-1, max_x-1)

def handle_selection():
	global process

	if len(results) == 0:
		return

	index = position + scroll
	if 'video' in results[index]:
		video = results[index]['video']
		if mode == 0:
			set_status("downloading: " + video)
			os.chdir(files_path)
			command = "youtube-dl -q --restrict-filenames " + video
			args = shlex.split(command)
			process = subprocess.Popen(args)
		else:
			os.chdir(files_path)
			command = play_command + " " + video
			args = shlex.split(command)
			try:
				play_process = subprocess.Popen(args)
				play_process.wait()
			except:
				return 1

	return 0

def delete_selection():
	if len(results) == 0:
		return

	index = position + scroll
	if mode == 1:
		file = results[index]['video']
		os.remove(files_path + file)

	return 0

def set_status(text):
	global menu_status, max_y, max_x
	menu_status.clear()
	menu_status.addstr(0, 0, text, curses.A_BOLD)
	menu_status.noutrefresh(0, 0, max_y-1, 0, max_y-1, max_x-1)

def main(stdscr):
	global position, mode, max_x, max_y, scroll, menu_status

	subreddit = "videos"
	search = ""
	screen = curses.initscr()
	curses.halfdelay(10)
	curses.curs_set(0)

	(max_y, max_x) = screen.getmaxyx()
	curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
	
	menu_results = curses.newpad(100, 300)
	menu_status = curses.newpad(1, 300)
	menu_help = curses.newpad(1, 300)
	draw_results(menu_results)
	draw_help(menu_help)
	curses.doupdate()

	while True:
		c = screen.getch()
		redraw = 0
		if c == curses.KEY_RESIZE:
			(max_y, max_x) = screen.getmaxyx()
			redraw = 1
		elif c == 10:
			status = handle_selection()
			if status == 1:
				set_status("Playback failed")
		elif c == ord('q'):
			break
		elif c == ord('d'):
			if mode == 1:
				delete_selection()
				menu_results.clear()
				load_downloads()
				if scroll + max_display > len(results):
					scroll = len(results) - max_display
					if scroll < 0:
						scroll = 0
				if position >= len(results):
					position -= 1
				set_status("p=" + str(position) + " s=" + str(scroll))
				redraw = 1

		elif c == ord('l'):
			mode = not mode 
			if mode == 0:
				load_subreddit(subreddit, search)
			elif mode == 1:
				load_downloads()
			menu_results.clear()
			position = 0
			scroll = 0
			redraw = 1
		elif c == ord('/'):
			mode = 0

			# get input
			curses.echo()
			curses.curs_set(1)
			text = "search /r/" + subreddit + ": "
			screen.addstr(max_y-2, 0, text)
			search = screen.getstr(max_y-2, len(text), 50).decode('utf-8')
			curses.noecho()
			curses.curs_set(0)

			# load results
			if search != "":
				position = 0
				scroll = 0
				load_subreddit(subreddit, search)
				menu_results.clear()
				redraw = 1
		elif c == ord('s'):
			mode = 0

			# get input
			curses.echo()
			curses.curs_set(1)
			text = "subreddit: "
			screen.addstr(max_y-2, 0, text)
			subreddit = screen.getstr(max_y-2, len(text)).decode('utf-8')
			curses.noecho()
			curses.curs_set(0)

			# load new subreddit
			if subreddit != "":
				position = 0
				scroll = 0
				load_subreddit(subreddit)
				menu_results.clear()
				redraw = 1
		elif c == ord('r'):
			if mode == 0:

				# load new subreddit
				if subreddit != "":
					position = 0
					scroll = 0
					load_subreddit(subreddit, force=1)
					menu_results.clear()
					redraw = 1
			elif mode == 1:
				menu_results.clear()
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
			if position >= max_display-1 and scroll < len(results) - max_display:
				scroll += 1
			elif position + scroll < len(results) - 1:
				position += 1
			redraw = 1

		if redraw:
			draw_results(menu_results)
			draw_help(menu_help)

		if process != None:
			if process.poll() == 0:
				set_status("done")

		curses.doupdate()

	curses.endwin()

load_subreddit("videos")
curses.wrapper(main)

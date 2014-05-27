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
files_path = os.path.expanduser("~/.cache/redpi/files")
cache_path = os.path.expanduser("~/.cache/redpi/")
os.makedirs(files_path, exist_ok=True)

play_command = "omxplayer"
#play_command = "vlc -q"

live = 1
position = 0
results_max = 20
results_count = 0
process = None
mode = 0
max_y = 0
max_x = 0
html_parser = html.parser.HTMLParser()

def load_subreddit(subreddit, search=""):
	global children, results_count
	if live == 1:
		if search == "":
			url = "http://www.reddit.com/r/" + subreddit + ".json"
		else:
			url = "http://www.reddit.com/r/" + subreddit + "/search.json?q=" + urllib.parse.quote(search) + "&restrict_sr=on"
		header = { 'User-Agent' : 'cool json bot' }
		request = urllib.request.Request(url, headers=header)
		try:
			response = urllib.request.urlopen(request)
		except:
			children = [] 
			results_count = 0
			return

		json_str = response.readall().decode("utf-8")
		decoded = json.loads(json_str)
		#print(json.dumps(decoded, sort_keys=True, indent=2))
	else:
		with open('test.json', 'r') as handle:
			decoded = json.load(handle)

	children = decoded['data']['children']
	del children[results_max:]
	results_count = len(children)

def draw_results(menu):

	if len(children) == 0:
		menu.addstr(0, 0, "No results")
		menu.noutrefresh(0, 0, 0, 0, max_y-1, max_x-1)
		return

	i = 0
	title_width = 46
	template = "{0:2} {1:5} {2:%s} {3:20}" % title_width
	for item in children:
		title = html_parser.unescape(item['data']['title'][:title_width])
		url = item['data']['url']
		ups = str(item['data']['ups'])
		domain = item['data']['domain'][:20]
		media = item['data']['media']
		row = [str(i+1), ups, title, domain]
		color = 1
		if position == i:
			color = 2
		menu.addstr(i, 0, template.format(*row), curses.color_pair(color))
		i += 1
		if i >= results_max:
			break

	menu.noutrefresh(0, 0, 0, 0, max_y-1, max_x-1)

def draw_downloads(menu):
	global results_count

	i = 0
	title_width = 70
	template = "{0:2} {1:%s}" % title_width

	files = os.listdir(files_path)
	if len(files) == 0:
		menu.addstr(0, 0, "No results")
		menu.noutrefresh(0, 0, 0, 0, max_y-1, max_x-1)
		return

	for file in files:
		row = [str(i+1), file[:title_width]]
		color = 1
		if position == i:
			color = 2
		menu.addstr(i, 0, template.format(*row), curses.color_pair(color))
		i += 1
		if i >= results_max:
			break

	results_count = i
	menu.noutrefresh(0, 0, 0, 0, max_y-1, max_x-1)

def handle_selection(menu):
	global children, process, play_command

	if mode == 0:
		item = children[position]['data']
		if item['media'] != None:
			media = item['media']['oembed']
			if media['type'] == "video":
				menu.addstr(0, 0, "downloading: " + item['url'])
				menu.noutrefresh(0, 0, max_y-1, 0, max_y-1, max_x-1)
				os.chdir(files_path)
				command = "youtube-dl -q --restrict-filenames " + item['url']
				args = shlex.split(command)
				process = subprocess.Popen(args)
	else:
		os.chdir(files_path)
		files = os.listdir(files_path)
		if len(files) > 0:
			command = play_command + " " + files[position]
			args = shlex.split(command)
			try:
				play_process = subprocess.Popen(args)
				play_process.wait()
			except:
				return 1

	return 0

def main(stdscr):
	global position, mode, max_x, max_y

	subreddit = "videos"
	screen = curses.initscr()
	curses.halfdelay(10)
	curses.curs_set(0)

	(max_y, max_x) = screen.getmaxyx()
	curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
	
	menu_results = curses.newpad(100, 300)
	menu_status = curses.newpad(1, 300)
	draw_results(menu_results)
	curses.doupdate()

	while True:
		c = screen.getch()
		redraw = 0
		if c == curses.KEY_RESIZE:
			(max_y, max_x) = screen.getmaxyx()
			redraw = 1
		elif c == 10:
			status = handle_selection(menu_status)
			if status == 1:
				menu_status.addstr(0, 0, "Playback failed")
				menu_status.noutrefresh(0, 0, max_y-1, 0, max_y-1, max_x-1)
		elif c == ord('q'):
			break
		elif c == ord('l'):
			mode = 1
			menu_results.clear()
			position = 0
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
				load_subreddit(subreddit)
				menu_results.clear()
				redraw = 1
		elif c == curses.KEY_UP or c == ord('k'):
			position -= 1
			if position < 0:
				position = 0
			redraw = 1
		elif c == curses.KEY_DOWN or c == ord('j'):
			position += 1
			if position > results_count - 1:
				position = results_count - 1
			redraw = 1

		if redraw:
			if mode == 0:
				draw_results(menu_results)
			else:
				draw_downloads(menu_results)

		if process != None:
			if process.poll() == 0:
				menu_status.clear()
				menu_status.addstr(0, 0, "done")
				menu_status.noutrefresh(0, 0, max_y-1, 0, max_y-1, max_x-1)

		curses.doupdate()

	curses.endwin()

load_subreddit("videos")
curses.wrapper(main)

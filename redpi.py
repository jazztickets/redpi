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
from subprocess import call
from html import unescape
#from time import gmtime, strftime
from urllib.parse import quote
from urllib.request import urlopen
#from curses import panel
from curses import wrapper

# create cache directory
files_path = os.path.expanduser("~/.cache/redpi/files")
cache_path = os.path.expanduser("~/.cache/redpi/")
os.makedirs(files_path, exist_ok=True)

live = 1
position = 0
results_max = 20
results_count = 0
process = None
mode = 0

def load_subreddit(subreddit, search=""):
	global children, results_count
	if live == 1:
		if search == "":
			url = "http://www.reddit.com/r/" + subreddit + ".json"
		else:
			url = "http://www.reddit.com/r/" + subreddit + "/search.json?q=" + urllib.parse.quote(search) + "&restrict_sr=on"
		header = { 'User-Agent' : 'cool json bot' }
		request = urllib.request.Request(url, headers=header)
		response = urllib.request.urlopen(request)
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
	menu.clear()

	i = 0
	title_width = 46
	template = "{0:2} {1:5} {2:%s} {3:20}" % title_width
	for item in children:
		title = unescape(item['data']['title'][:title_width])
		url = item['data']['url']
		ups = str(item['data']['ups'])
		domain = item['data']['domain'][:20]
		media = item['data']['media']
		row = [str(i+1), ups, title, domain]
		#print(template.format(*row))
		color = 1
		if position == i:
			color = 2
		menu.addstr(i, 0, template.format(*row), curses.color_pair(color))
		i += 1
		if i >= results_max:
			break

	menu.refresh()

def draw_downloads(menu):
	global results_count
	menu.clear()

	i = 0
	title_width = 70
	template = "{0:2} {1:%s}" % title_width

	files = os.listdir(files_path)
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
	menu.refresh()

def handle_selection(menu):
	global children, process

	if mode == 0:
		item = children[position]['data']
		if item['media'] != None:
			media = item['media']['oembed']
			if media['type'] == "video":
				menu.addstr(1, 0, "downloading: " + item['url'])
				menu.refresh()
				os.chdir(files_path)
				command = "youtube-dl -q " + item['url']
				args = shlex.split(command)
				process = subprocess.Popen(args)
	else:
		os.chdir(files_path)
		#command = "youtube-dl -q " + item['url']
		#args = shlex.split(command)
		#process = subprocess.Popen(args)

def main(stdscr):
	global position, mode

	subreddit = "videos"
	screen = curses.initscr()
	curses.curs_set(0)

	curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
	
	menu_results = curses.newwin(100, 200, 0, 0)
	menu_status = curses.newwin(3, 200, results_max + 1, 0)
	draw_results(menu_results)

	#panel = curses.panel.new_panel(menu)
	#panel.top()
	#panel.show()

	while True:
		c = screen.getch()
		if c == 10:
			handle_selection(menu_status)
		elif c == ord('q'):
			break
		elif c == ord('l'):
			mode = 1
			position = 0
		elif c == ord('/'):
			mode = 0

			# get input
			curses.echo()
			curses.curs_set(1)
			text = "search /r/" + subreddit + ": "
			menu_status.addstr(0, 0, text)
			menu_status.refresh()
			search = menu_status.getstr(0, len(text), 50).decode('utf-8')
			curses.noecho()
			curses.curs_set(0)

			# load new subreddit
			if search != "":
				position = 0
				load_subreddit(subreddit, search)
				menu_status.clear()
		elif c == ord('s'):
			mode = 0

			# get input
			curses.echo()
			curses.curs_set(1)
			menu_status.addstr(0, 0, "subreddit: ")
			menu_status.refresh()
			subreddit = menu_status.getstr(0, 11, 50).decode('utf-8')
			curses.noecho()
			curses.curs_set(0)

			# load new subreddit
			if subreddit != "":
				position = 0
				load_subreddit(subreddit)
				menu_status.clear()
		elif c == curses.KEY_UP or c == ord('k'):
			position -= 1
			if position < 0:
				position = 0
		elif c == curses.KEY_DOWN or c == ord('j'):
			position += 1
			if position > results_count - 1:
				position = results_count - 1

		if mode == 0:
			draw_results(menu_results)
		else:
			draw_downloads(menu_results)

		if process != None:
			if process.poll() == 0:
				menu_status.clear()
				menu_status.addstr(1, 0, "done")
				menu_status.refresh()

	curses.endwin()

load_subreddit("videos")
wrapper(main)

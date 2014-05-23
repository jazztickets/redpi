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
from subprocess import call
from html import unescape
#from time import gmtime, strftime
from urllib.parse import quote
from urllib.request import urlopen
#from curses import panel
from curses import wrapper

live = 1
position = 0
results_max = 25
title_width = 46
template = "{0:2} {1:5} {2:%s} {3:20}" % title_width
process = None

def load_subreddit(subreddit, search=""):
	global children
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

def draw_menu(menu):
	menu.clear()

	i = 0
	for item in children:
		title = unescape(item['data']['title'][:title_width])
		url = item['data']['url']
		ups = str(item['data']['ups'])
		domain = item['data']['domain']
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

def handle_selection(menu):
	global children, process
	item = children[position]['data']
	if item['media'] != None:
		media = item['media']['oembed']
		if media['type'] == "video":
			menu.addstr(1, 0, "downloading: " + item['url'])
			menu.refresh()
			command = "youtube-dl -q " + item['url']
			args = shlex.split(command)
			process = subprocess.Popen(args)

def main(stdscr):
	global position

	subreddit = "videos"
	screen = curses.initscr()
	curses.curs_set(0)

	curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
	
	menu_results = curses.newwin(results_max, 80, 0, 0)
	menu_status = curses.newwin(3, 80, results_max + 1, 0)
	draw_menu(menu_results)

	#panel = curses.panel.new_panel(menu)
	#panel.top()
	#panel.show()

	while True:
		c = screen.getch()
		if c == 10:
			handle_selection(menu_status)
		elif c == ord('q'):
			break
		elif c == ord('/'):

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
				draw_menu(menu_results)
		elif c == ord('s'):

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
				draw_menu(menu_results)
		elif c == curses.KEY_UP or c == ord('k'):
			position -= 1
			if position < 0:
				position = 0
		elif c == curses.KEY_DOWN or c == ord('j'):
			position += 1
			if position > len(children) - 1:
				position = len(children) - 1

		draw_menu(menu_results)

		if process != None:
			if process.poll() == 0:
				menu_status.clear()
				menu_status.addstr(1, 0, "done")
				menu_status.refresh()

	curses.endwin()

load_subreddit("videos")
wrapper(main)

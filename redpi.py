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
import http.server
import threading
import socketserver
import logging
import re
from socket import gethostbyname, gethostname
from urllib.parse import quote, urlparse, parse_qs
from urllib.request import urlopen
from http.client import HTTPConnection

script_path = os.path.dirname(os.path.realpath(__file__))

# create cache directory
cache_path = os.path.expanduser("~/.cache/redpi/")
files_path = os.path.expanduser("~/.cache/redpi/files/")
images_path = os.path.expanduser("~/.cache/redpi/images/")
os.makedirs(cache_path, exist_ok=True)
os.makedirs(files_path, exist_ok=True)
os.makedirs(images_path, exist_ok=True)

logging.basicConfig(filename=cache_path+'debug.log', level=logging.DEBUG, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S %p')
logging.debug("starting redpi")

youtube_key = "AIzaSyDBtXPQRsI7Ny7JZ335nq-4VGLfOk4dSJI"
twitch_key = "oluqw7uf9dy4gad4vdrakqy38pz5vsj"

port = 8080
if len(sys.argv) == 2:
	try:
		port = int(sys.argv[1])
	except:
		port = 8080

hostname = ""

mode_results = {
	"downloads" : [],
	"reddit" : [],
	"youtube" : [],
	"twitch" : []
}

mode_status = {
	"downloads" : "",
	"reddit" : "type s to select subreddit",
	"youtube" : "type / to search youtube",
	"twitch" : ""
}

mode_query = {
	"downloads" : "",
	"reddit" : "",
	"youtube" : "",
	"twitch" : ""
}

mode_help = {
	"downloads" : "1: downloads 2: reddit 3: youtube 4. twitch /: find m: movie a: playall d: delete r: refresh q: quit",
	"reddit" : "1: downloads 2: reddit 3: youtube 4. twitch s: subreddit /: search r: refresh q: quit",
	"youtube" : "1: downloads 2: reddit 3: youtube 4. twitch c: channel /: search t: thumb q: quit",
	"twitch" : "1: downloads 2: reddit 3: youtube 4. twitch g: games r: refresh c: open chat q: quit"
}

if platform.machine()[:3] == "arm":
	play_command = "omxplayer"
	movie_command = "pasuspender -- omxplayer -b -p -o hdmi -n 2"
	view_command = "fbi"
	stream_player = "omxplayer --fifo"
	stream_command = "livestreamer"
	stream_quality = "1080p60,best"
	stream_chat = False
else:
	play_command = "xdg-open"
	movie_command = "xdg-open"
	view_command = "xdg-open"
	stream_player = ""
	stream_command = "mpv --af=acompressor --quiet"
	stream_quality = ""
	stream_chat = True

DEVNULL = open(os.devnull, "w")
position = 0
expire_time = 600
max_display = 20
screen = None
downloads = []
download_process = None
play_process = None
menu_status = None
menu_help = None
scroll = 0
current_dir = ""
mode = 'downloads'
sub_mode = ''
max_y = 0
max_x = 0
done = 0
html_parser = html.parser.HTMLParser()

class HttpHandler(http.server.BaseHTTPRequestHandler):

	def log_message(self, format, *args):
		pass

	def do_HEAD(s):
		s.send_response(200)
		s.send_header("Content-type", "text/html")
		s.end_headers()

	def do_GET(s):
		global script_path, play_process, menu_results, position, scroll

		# parse url
		url_data = urlparse(s.path)
		path = url_data.path
		query = parse_qs(url_data.query)

		# show web controls
		if path == "/":
			with open(script_path + '/index.html', 'r') as infile:
				content = infile.read()

			s.send_response(200)
			s.send_header("Content-type", "text/html")
			s.send_header("Content-Length", len(content))
			s.end_headers()
			s.wfile.write(str.encode(content))
			return

		# send header
		s.send_response(200)
		s.send_header("Content-type", "text/html")
		s.end_headers()

		# choose action
		if path == "/download":
			url = re.search("(https?://.+)", query['url'][0])
			if url:
				video = url.group(1)
				download_video(video)
		elif path == "/test":
			client_host, client_port = s.client_address
			client_string = client_host + ":" + str(client_port)

			set_status("test button hit from " + client_string)
		elif path == "/command":
			action = query['action'][0]
			if action == "up":
				go_up()
			elif action == "down":
				go_down()
			elif action == "enter":
				(status, redraw) = handle_selection(False, False)
				if redraw == 1:
					menu_results.erase()
					position = 0
					scroll = 0
					draw_results()
					draw_help()
			elif action == "downloads":
				go_change_screen('downloads')
			elif action == "reddit":
				go_change_screen('reddit')
			elif action == "youtube":
				go_change_screen('youtube')
			elif action == "twitch":
				go_change_screen('twitch')

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
	pass

def parse_youtube_api(url):
	api_url = "https://www.googleapis.com/youtube/v3/search?key=" + youtube_key + "&" + url

	request = urllib.request.Request(api_url)
	try:
		response = urllib.request.urlopen(request)
	except:
		return

	# get json object
	json_str = response.read().decode("utf-8")
	decoded = json.loads(json_str)

	return decoded['items']

def load_youtube(search="", channel=False):
	global mode_results

	set_status("searching youtube for \"" + search + "\"")

	# build url
	if channel:
		url = "type=channel&part=id&maxResults=1&q=" + urllib.parse.quote(search)
		children = parse_youtube_api(url)

		channel_id = children[0]['id']['channelId']
		url = "type=video&part=snippet&maxResults=50&channelId=" + channel_id + "&order=date"
	else:
		url = "type=video&part=snippet&maxResults=50&q=" + urllib.parse.quote(search)

	# get results
	mode_results['youtube'] = []
	children = parse_youtube_api(url)

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
		thumbnail = item['snippet']['thumbnails']['high']['url']
		tdate = time.strptime(published_at, "%Y-%m-%dT%H:%M:%S.%fZ")

		# build row
		row = [str(i+1), title, channel, time.strftime("%m-%d-%Y", tdate)]

		data = {}
		data['display'] = template.format(*row)
		data['video'] = id
		data['thumbnail'] = thumbnail
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

		json_str = response.read().decode("utf-8")
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
		data['url'] = item['data']['url']
		mode_results['reddit'].append(data)
		i += 1

	mode_status['reddit'] = status_string
	set_status(status_string)

def load_twitch_games():
	global mode_results

	set_status("loading twitch.tv games")

	# build url
	url = "https://api.twitch.tv/kraken/games/top?limit=100&client_id=" + twitch_key

	# get results
	mode_results['twitch'] = []
	request = urllib.request.Request(url)
	try:
		response = urllib.request.urlopen(request)
	except:
		return

	# get json object
	json_str = response.read().decode("utf-8")
	decoded = json.loads(json_str)

	# get children
	children = decoded['top']

	# build results
	i = 0
	count_width = 2
	viewers_width = 8
	title_width = max_x - (count_width+1) - (viewers_width+1) - 0
	template = "{0:%s} {1:%s} {2:%s}" % (count_width, title_width, viewers_width)
	for item in children:
		id = item['game']['name']
		title = item['game']['name'][:title_width]
		viewers = str(item['viewers'])[:viewers_width]

		# build row
		row = [str(i+1), title, viewers]

		data = {}
		data['display'] = template.format(*row)
		data['video'] = id
		data['type'] = 'game'
		mode_results['twitch'].append(data)
		i += 1

	mode_status['twitch'] = "twitch.tv games"
	set_status(mode_status['twitch'])

def load_twitch_streams():
	global mode_results, sub_mode
	game = sub_mode

	set_status("loading twitch.tv streams for " + game)

	# build url
	url = "https://api.twitch.tv/kraken/streams?limit=100&client_id=" + twitch_key + "&game=" + urllib.parse.quote(game)

	# get results
	mode_results['twitch'] = []
	request = urllib.request.Request(url)
	try:
		response = urllib.request.urlopen(request)
	except:
		return

	# get json object
	json_str = response.read().decode("utf-8")
	decoded = json.loads(json_str)

	# get children
	children = decoded['streams']

	# build results
	i = 0
	count_width = 2
	viewers_width = 8
	name_width = 20
	title_width = max_x - (count_width+1) - (viewers_width+1) - (name_width+1) - 0
	template = "{0:%s} {1:%s} {2:%s} {3:%s}" % (count_width, title_width, name_width, viewers_width)
	for item in children:
		if 'url' in item['channel']:
			id = item['channel']['url']
			if item['channel']['status'] != None:
				title = item['channel']['status'][:title_width]
			else:
				title = item['channel']['display_name'][:title_width]
			name = item['channel']['display_name'][:name_width]
			viewers = str(item['viewers'])[:viewers_width]

			# build row
			row = [str(i+1), title, name, viewers]

			data = {}
			data['display'] = template.format(*row)
			data['video'] = id
			data['type'] = 'stream'
			mode_results['twitch'].append(data)
			i += 1

	mode_status['twitch'] = "twitch.tv streams for " + game
	set_status(mode_status['twitch'])

def load_downloads():
	global mode_results

	# list files in current path
	browse_path = os.path.join(files_path, current_dir)
	list = os.listdir(browse_path)
	dirs = []
	files = []

	if current_dir != "":
		dirs.append("..")

	# create lists for dirs and files
	for file in list:
		path = os.path.join(browse_path, file)
		try:
			os.stat(path)
			if os.path.isdir(path):
				if file[0] != ".":
					dirs.append(file)
			else:
				files.append(file)
		except:
			pass

	# sort lists
	dirs.sort()
	files.sort(key=lambda file: os.path.getctime(os.path.join(browse_path, file)))

	# merge dirs with files
	files = dirs + files

	# build list of downloads
	mode_results['downloads'] = []
	i = 0
	count_width = 2
	date_width = 19
	title_width = max_x - (count_width+1) - (date_width+1)
	template = "{0:%s} {1:%s} {2:%s}" % (count_width, title_width, date_width)
	for file in files:

		data = {}
		data['video'] = file
		data['isdir'] = os.path.isdir(os.path.join(browse_path, file))
		if file == '..':
			data['isdir'] = True

		full_path = os.path.join(browse_path, file)
		date_string = ""
		if os.path.isfile(full_path) and not data['isdir']:
			cdate = time.localtime(os.path.getctime(full_path))
			date_string = time.strftime("%Y-%m-%d %I:%M %p", cdate)

		row = [str(i+1), file[:title_width], date_string]

		data['display'] = template.format(*row)
		mode_results['downloads'].append(data)
		i += 1

	clamp_cursor()
	set_status(str(download_count()) + " download(s) in progress")

def draw_results():
	global menu_results

	if len(mode_results[mode]) == 0:
		menu_results.addstr(0, 0, "No results")
	else:
		i = 0
		for row in mode_results[mode][scroll : scroll + max_display]:
			color = 1

			# partial downloads
			if mode == 'downloads' and row['video'].endswith(".part"):
				color = 3

			# directory
			if 'isdir' in row and row['isdir']:
				color = 5

			# if selected set highlight color
			if position == i:
				color += 1

			# draw row
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
	global play_process
	if play_process != None:
		return

	draw_help()
	draw_results()
	curses.halfdelay(10)

def play_video(file, movie_mode=False):
	global screen, play_process, DEVNULL

	os.chdir(files_path)

	# start play command
	if movie_mode:
		command = movie_command
	else:
		command = play_command

	# add file path
	command += " \"" + file.replace("\"", "\\\"") + "\""

	args = shlex.split(command)
	try:
		screen.clear()
		screen.refresh()

		logging.debug("playing " + file)
		play_process = subprocess.Popen(args, stdout=DEVNULL, stderr=DEVNULL)
		play_process.wait()

		logging.debug("finished playing " + file)
		set_status("finished playing " + file)
		play_process = None

		load_downloads()
		restore_state()
	except:
		set_status("playback failed")
		play_process = None

		restore_state()
		return 1

	return 0

def stream_video(url, open_chat):
	global screen, play_process, stream_quality, stream_chat, DEVNULL

	os.chdir(files_path)
	command = stream_command + " " + url + " " + stream_quality
	if stream_player != "":
		command = command + " --player " + stream_player

	lex = shlex.shlex(command)
	lex.whitespace_split = True
	args = list(lex)
	try:
		screen.clear()
		screen.refresh()

		set_status("starting stream")

		if stream_chat and open_chat:
			chat_command = "xdg-open " + url + "/chat"
			chat_lex = shlex.shlex(chat_command)
			chat_lex.whitespace_split = True
			chat_args = list(chat_lex)

			chat_process = subprocess.Popen(chat_args, stderr=DEVNULL)
			chat_process.wait()

		lex = shlex.shlex(command)
		lex.whitespace_split = True
		args = list(lex)

		play_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		while True:
			line = play_process.stdout.readline()
			if not line:
				break
			set_status(line.decode('utf-8'))
			logging.debug(line)

		play_process.wait()

		set_status("finished stream")
		play_process = None

		restore_state()

	except:

		set_status("playback failed")
		play_process = None

		restore_state()
		return 1

	return 0

def view_image(url):
	global screen, play_process, DEVNULL

	# download to images directory
	os.chdir(images_path)

	try:

		# build download commmand
		command = "wget " + url + " -O image"
		lex = shlex.shlex(command)
		lex.whitespace_split = True
		args = list(lex)

		# download image
		download_process = subprocess.Popen(args, stderr=DEVNULL)
		download_process.wait()

		# clear screen
		screen.clear()
		screen.refresh()

		# build view command
		command = view_command + " " + "image"
		lex = shlex.shlex(command)
		lex.whitespace_split = True
		args = list(lex)

		# view image
		play_process = subprocess.Popen(args, stderr=DEVNULL)
		play_process.wait()

		set_status("finished viewing image")
		play_process = None

		restore_state()

	except:

		set_status("view image failed")
		play_process = None

		restore_state()
		return 1

	return 0

def show_thumbnail():
	global current_dir, sub_mode

	# get data array from results page
	data = mode_results[mode]

	# check for empty data
	if len(data) == 0:
		return (0, 0)

	# get index into array
	index = position + scroll

	# get thumbnail url
	thumbnail = None
	if 'thumbnail' in data[index]:
		thumbnail = data[index]['thumbnail']

	view_image(thumbnail)

# returns status, redraw
def handle_selection(open_chat=False, movie_mode=False):
	global current_dir, sub_mode

	# get data array from results page
	data = mode_results[mode]

	# check for empty data
	if len(data) == 0:
		return (0, 0)

	# get index into array
	index = position + scroll

	# get video id or url
	video = None
	if 'video' in data[index]:
		video = data[index]['video']

	if mode == 'twitch':
		if data[index]['type'] == 'game':
			sub_mode = video
			load_twitch_streams()
			return (0, 1)
		else:
			return (stream_video(video, open_chat), 0)
	elif mode == 'downloads':
		if data[index]['isdir']:
			current_dir = os.path.join(current_dir, video)
			current_dir = os.path.relpath(os.path.abspath(files_path + current_dir), files_path)
			if current_dir == ".":
				current_dir = ""
			load_downloads()
			set_status(current_dir)
			return (0, 1)
		else:
			return (play_video(os.path.join(current_dir, video), movie_mode), 0)
	elif mode == 'youtube':
		download_video(video)
	else:

		# check for video from reddit
		if video != None:
			download_video(video)
		# might be an image
		else:
			url = data[index]['url']

			# attempt to fix bad imgur links
			search = re.search("//imgur.com/(.*)", url)
			if search:
				url = "http://i.imgur.com/" + search.group(1) + ".jpg"

			# get content type of url
			content_type = get_content_type(url)
			if content_type:

				# view image
				is_image = re.search("image/", content_type)
				if is_image:
					view_image(url)
					return (0, 0)

			set_status("Not image or video")

	return (0, 0)

def find_result(query, start_from):
	data = mode_results[mode]
	count = len(data)

	index = start_from
	for i in range(0, count):

		if index >= count:
			index = 0

		match = re.search(re.escape(query), data[index]['video'], flags=re.IGNORECASE)
		if match:
			return index

		index += 1

	return -1

def get_content_type(url):
	parsed = urlparse(url)
	connection = HTTPConnection(parsed.netloc)
	connection.request('HEAD', parsed.path + '?' + parsed.query)
	response = connection.getresponse()

	return response.getheader('content-type')

def download_count():
	global downloads, download_process
	count = len(downloads)
	if download_process != None:
		count += 1

	return count

def download_video(video):
	global downloads, play_process

	logging.debug("appending download " + video)
	downloads.append(video)
	if play_process == None:
		set_status(str(download_count()) + " download(s) in progress - adding " + video + " to queue")
	restore_state()

def process_download_queue():
	global done, downloads, download_process, menu_results

	# loop until program is finished
	while not done:

		# check for existing download
		if download_process != None:
			download_process.poll()
			if download_process.returncode != None:
				download_process = None
				logging.debug("finished download process")

				# set status if nothing is playing
				if play_process == None:
					set_status(str(download_count()) + " download(s) in progress - download finished")
					menu_results.erase()
					load_downloads()
					draw_results()
		elif download_process == None and len(downloads) > 0:

			# get next download in queue
			video = downloads.pop(0);
			logging.debug("popping download queue " + video)

			# run youtube-dl
			os.chdir(files_path)
			command = "youtube-dl -q --restrict-filenames -f \"best[ext=mp4]\" -- " + video
			args = shlex.split(command)
			download_process = subprocess.Popen(args)

			# set status if nothing is playing
			if play_process == None:
				set_status(str(download_count()) + " download(s) in progress - downloading: " + video)

		time.sleep(1)

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

def clamp_cursor():
	global position, scroll, mode_results, mode
	#logging.debug("position = " + str(position))
	#logging.debug("scroll = " + str(scroll))
	#logging.debug("len(mode_results[mode]) = " + str(len(mode_results[mode])))
	if position + scroll >= len(mode_results[mode]) - 1:
		position = len(mode_results[mode]) - 1 - scroll
		if position < 0:
			scroll += position
			position = 0
			if scroll < 0:
				scroll = 0

def delete_selection():
	global current_dir
	if len(mode_results[mode]) == 0:
		return

	index = position + scroll
	if mode == 'downloads':
		file = os.path.join(os.path.join(files_path, current_dir), mode_results[mode][index]['video'])
		if os.path.isfile(file):
			os.remove(file)

	set_status("deleted " + file)

	return 0

def set_status(text):
	global menu_status
	menu_status.erase()
	try:
		menu_status.addstr(0, 0, text[:max_x], curses.A_BOLD)
	except curses.error:
		pass
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

def go_change_screen(screen):
	global mode, mode_results, mode_status, position, scroll

	mode = screen
	if screen == 'downloads':
		load_downloads()
	elif screen == 'twitch':
		if len(mode_results[mode]) == 0:
			load_twitch_games()

	menu_results.erase()
	if mode_status[mode] != "":
		set_status(mode_status[mode])

	position = 0
	scroll = 0
	draw_results()
	draw_help()

def go_up():
	global position, scroll

	if position <= 0 and scroll > 0:
		scroll -= 1
	elif position + scroll > 0:
		position -= 1

	draw_results()
	draw_help()

def go_down():
	global position, scroll, max_display, mode_results

	if position >= max_display-1 and scroll < len(mode_results[mode]) - max_display:
		scroll += 1
	elif position + scroll < len(mode_results[mode]) - 1:
		position += 1

	draw_results()
	draw_help()

def main(stdscr):
	global done, downloads, position, mode, max_x, max_y, scroll, menu_status, menu_results, menu_help, max_display, screen, sub_mode, port

	server = None
	if port != 0:
		ThreadedTCPServer.allow_reuse_address = True
		server = ThreadedTCPServer((hostname, port), HttpHandler)

		server_thread = threading.Thread(target=server.serve_forever)
		server_thread.daemon = True
		server_thread.start()

	download_thread = threading.Thread(target=process_download_queue)
	download_thread.daemon = True
	download_thread.start()

	subreddit = ""
	search = ""
	screen = curses.initscr()
	curses.curs_set(0)

	(max_y, max_x) = screen.getmaxyx()
	max_display = max_y - 4
	curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_RED)
	curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_BLACK)
	curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_RED)
	curses.init_pair(5, curses.COLOR_GREEN, curses.COLOR_BLACK)
	curses.init_pair(6, curses.COLOR_GREEN, curses.COLOR_RED)

	menu_results = curses.newpad(100, 300)
	menu_status = curses.newpad(1, 300)
	menu_help = curses.newpad(1, 300)
	restore_state()

	load_downloads()
	draw_results()
	draw_help()
	if server:
		set_status("web server started on " + gethostbyname(gethostname()) + ":" + str(port))

	curses.doupdate()
	while True:
		c = screen.getch()
		redraw = 0
		if c == curses.KEY_RESIZE:
			(max_y, max_x) = screen.getmaxyx()
			max_display = max_y - 4
			menu_results.clear()
			redraw = 1
		elif c == 6 or c == 338:
			# ^F or pagedown
			for i in range(0, max_display-1):
				if position >= max_display-1 and scroll < len(mode_results[mode]) - max_display:
					scroll += 1
				elif position + scroll < len(mode_results[mode]) - 1:
					position += 1
			redraw = 1
		elif c == 2 or c == 339:
			# ^B or pageup
			for i in range(0, max_display-1):
				if position <= 0 and scroll > 0:
					scroll -= 1
				elif position + scroll > 0:
					position -= 1
			redraw = 1
		elif c == 10 or c == ord('c') or c == ord('m'):
			if mode == 'youtube' and c == ord('c'):

				# get input
				channel = get_input("channel: ", screen)

				# load channel
				position = 0
				scroll = 0
				search = ""
				sub_mode = ""
				load_youtube(channel, True)
				menu_results.erase()
				redraw = 1
			else:
				open_chat = False
				if c == ord('c'):
					open_chat = True

				movie_mode = False
				if c == ord('m'):
					movie_mode = True

				(status, redraw) = handle_selection(open_chat, movie_mode)
				if redraw == 1:
					menu_results.erase()
					position = 0
					scroll = 0
		elif c == ord('1'):
			go_change_screen('downloads')
		elif c == ord('2'):
			go_change_screen('reddit')
		elif c == ord('3'):
			go_change_screen('youtube')
		elif c == ord('4'):
			go_change_screen('twitch')
		elif c == ord('a'):
			if mode == 'downloads':
				handle_playall(screen)
		elif c == ord('q'):
			if server:
				server.shutdown()
				server.server_close()
			break
		elif c == ord('d'):
			if mode == 'downloads':
				delete_selection()
				menu_results.erase()
				load_downloads()
				update = len(mode_results[mode]) - (scroll + max_display)
				if update < 0 and len(mode_results[mode]) >= max_display:
					scroll += update
					position -= update
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

				# load search results
				if query != "":
					position = 0
					scroll = 0
					load_youtube(query)
					menu_results.erase()
					redraw = 1
			elif mode == 'downloads':

				# get input
				mode_query[mode] = get_input("find: ", screen)

				# find item
				if mode_query[mode] != "":
					new_scroll = find_result(mode_query[mode], 0)
					if new_scroll == -1:
						set_status("not found")
					else:
						position = 0
						scroll = new_scroll

					menu_results.erase()
					redraw = 1

		elif c == ord('t'):
			if mode == 'youtube':
				show_thumbnail()
		elif c == ord('n'):
			if mode == 'downloads':

				# find item
				if mode_query[mode] != "":
					new_scroll = find_result(mode_query[mode], position + scroll + 1)
					if new_scroll == -1:
						set_status("not found")
					else:
						position = 0
						scroll = new_scroll

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
		elif c == ord('g'):
			if mode == 'twitch':

				# load twitch games
				position = 0
				scroll = 0
				search = ""
				sub_mode = ""
				load_twitch_games()
				menu_results.erase()
				redraw = 1
		elif c == ord('r'):
			if mode == 'reddit':
				load_subreddit(subreddit, search, force=1)
				menu_results.erase()
				redraw = 1
			elif mode == 'downloads':
				menu_results.erase()
				load_downloads()
				redraw = 1
			elif mode == 'twitch':
				menu_results.erase()
				if sub_mode == "":
					load_twitch_games()
				else:
					load_twitch_streams()
				redraw = 1
			clamp_cursor()
		elif c == curses.KEY_UP or c == ord('k'):
			go_up()
		elif c == curses.KEY_DOWN or c == ord('j'):
			go_down()

		if redraw:
			draw_results()
			draw_help()

		curses.doupdate()

	curses.endwin()
	done = 1
	download_thread.join()

curses.wrapper(main)

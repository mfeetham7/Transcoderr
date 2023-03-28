import argparse
import json
import os
import platform
import re
import subprocess
import sys                                                             

os_type = platform.system()
default_handbrake_exe = 'HandBrakeCLI.exe' if os_type == 'Windows' else 'HandBrakeCLI' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
get_bitrate_executable = 'ffmpeg.exe' if os_type == 'Windows' else 'ffmpeg' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
traversed_directories = set()
transcode_queue = set()
transcoded_files = set()
transcode_number = 1
starting_transcode_queue_length = 0
number_of_skipped_items = 0
preset_file = None
skip_all = False

#ANSI Escape Characters
BOLD = "\033[1m"
ITALIC = '\033[3m'
UNDERLINE = "\033[4m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
BLACK = "\033[30m"
BLUE = "\033[34m"
WHITE = "\033[37m"
BLINK_SLOW = "\033[5m"
BLINK_FAST = "\033[6m"

#Theme
BACKGROUND = "\033[40m" #Background Colors: Black: "\033[40m", Red: "\033[41m", Green: "\033[42m", Yellow: "\033[43m", Blue: "\033[44m", Magenta: "\033[45m", Cyan: "\033[46m", White: "\033[47m"
RESET = f"\033[0m{BACKGROUND}"
C1 = f"{RESET}{GREEN}" #Color 1
C2 = f"{RESET}{MAGENTA}" #Color 2
C3 = f"{RESET}{BLUE}" #Color 3
CF = f"{RESET}{CYAN}" #Files
CE = f"{RESET}{RED}{BLINK_SLOW}" #Error
CW = f"{RESET}{BOLD}{YELLOW}" #Warning
CI = f"{RESET}{BOLD}{WHITE}" #Info


def log_error(file, message):
    with open('brokenfiles.txt', 'a') as f:
        f.write(f'{file}: {message}\n')

def get_duration_ffprobe(file, ffprobe_exe='ffprobe'):
    try:
        result = subprocess.run([ffprobe_exe, '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', file], capture_output=True, text=True, encoding='utf-8')
        media_info = json.loads(result.stdout)
        if 'format' in media_info:
            duration_seconds = float(media_info['format']['duration'])
            duration_hours, remainder = divmod(duration_seconds, 3600)
            duration_minutes, duration_seconds = divmod(remainder, 60)
            return duration_hours, duration_minutes, duration_seconds
        else:
            return None
    except Exception as e:
        f = str(e) + ' Deleting and re-transcoding...\n'
        log_error(file, f)
        return None

def get_bitrate(file):
    global get_bitrate_executable
    try:
        result = subprocess.run([get_bitrate_executable, '-i', file, '-hide_banner', '-vn'], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        result = result.stderr
    except subprocess.CalledProcessError as e:
        result = e.stderr
    if not result:
        error_message = f"{CE}Error: {get_bitrate_executable} is not producing any output for the file {CF}{file}{CE}. Make sure the ffmpeg executable is installed and the file is a valid media file.{RESET}"
        print(f"{CE}{error_message}{RESET}")
        log_error(file, error_message)
        return None
    bitrate_regex = re.compile(r'bitrate: (\d+(\.\d+)?) (k|M)b/s')
    match = bitrate_regex.search(result)
    if match:
        bitrate = float(match.group(1))
        unit = match.group(3)
        if unit == 'M':
            bitrate *= 1000000
        elif unit == 'k':
            bitrate *= 1000
        return int(bitrate)
    else:
        warning_message = f"{CW}Warning: {get_bitrate_executable} is not producing any bitrate information for the file {CF}{file}{CW}. Make sure the ffmpeg executable is installed and the file is a valid media file.{RESET}"
        print(f"{CW}{warning_message}{RESET}")
        log_error(file, warning_message)
        return None

def get_output_file(input_file, export_path):
    global transcode_number
    global number_of_skipped_items
    global skip_all
    base_dir = args.import_path
    input_dir = os.path.dirname(input_file)
    input_filename = os.path.splitext(os.path.basename(input_file))[0]
    output_dir = os.path.join(export_path, os.path.relpath(input_dir, base_dir).replace('\\', os.path.sep))
    output_filename = f"{input_filename}.mkv"
    output_file = os.path.join(output_dir, output_filename)
    if os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        file_size_mb = int(file_size) / (1024 * 1024)
        file_duration = get_duration_ffprobe(output_file)
        if file_size == 0 or file_duration == 0 or file_size == None or file_duration == None:
            print(f"{CW}Output file {CF}{output_file}{CW} is corrupt (size: {CI}{file_size_mb:.2f} MB{CW}, duration: {CI}{file_duration}{CW}). {CE}Deleting and re-transcoding.{RESET}")
            os.remove(output_file)
            return output_file
        else:
            if skip_all == True:
                confirm = 'yes'
            else:
                print(f"{CF}{output_file}{CW} already exists.\nDo you want to overwrite that? {C2}y{CW}es, {C2}n{CW}o, {C2}s{CW}kip{RESET}")
                confirm = input().lower()
            if confirm == 'overwrite' or confirm == 'y' or confirm == 'yes':
                return output_file
            elif confirm == 'n' or confirm == 'no':
                file_root, file_ext = os.path.splitext(input_file)
                output_file = f"{file_root}_transcoded{file_ext}"
                return output_file
            elif confirm == 'skip' or confirm == 's':
                return 'null'
            elif confirm == 'skip all':
                skip_all = True
                print(f"\n{CW}Skipping existing file{RESET}")
                number_of_skipped_items += 1
                return 'null'
            else:
                return get_output_file(input_file, export_path)
    else: 
        return output_file

def transcode(input_file, export_path, target_bitrate=None):
    if export_path == 'null':
        return
    output_dir = os.path.dirname(export_path)
    global transcode_number
    global transcoded_files
    global starting_transcode_queue_length
    global default_handbrake_exe
    global preset_file
    if transcode_number == 1:
        starting_transcode_queue_length = len(transcode_queue)
    os.makedirs(output_dir, exist_ok=True)

    def process_output(output_line):
        encoding_status_pattern = re.compile(
            r'Encoding: task (?P<task_num>\d+) of (?P<total_tasks>\d+), '
            r'(?P<percent>\d+\.\d+) %.*ETA (?P<eta>\d{2}h\d{2}m\d{2}s)'
        )
        match = encoding_status_pattern.search(output_line)
        if match:
            print(f"\r{C1}Encoding Task {match.group('task_num')} of {match.group('total_tasks')}."f"Progress: {match.group('percent')}%, ETA: {match.group('eta')}{RESET}",end='',flush=True,)
    print(f'{C2}Transcoding{RESET}: {CF}{input_file}{C2}\nto{RESET}: {CF}{export_path}{C2}...{RESET}')
    cmd = [
        default_handbrake_exe,
        '-i', input_file,
        '-o', export_path,
        '--all-audio',
        '--audio-lang-list', 'all',
        '--all-subtitles',
        '--subtitle-lang-list', 'all',
    ]
    if preset_file:
        cmd.extend(['--preset-import-file', preset_file])
    else:
        cmd.extend([
            '--encoder', 'nvenc_h264',
            '-b', str(target_bitrate * 1024),
            '--cfr',
            '--vfr',
            '--no-detelecine',
            '--no-decomb',
            '--no-deblock',
            '--no-grayscale',
            '--custom-anamorphic',
            '--keep-display-aspect',
            '--preset', 'Very Fast 1080p30',
        ])
    print(f"{C2}Transcoding file {CI}{transcode_number}{C2} of {CI}{starting_transcode_queue_length}{RESET}")
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as process:
        for line in process.stdout:
            process_output(line)
    process.wait()
    input_filename = os.path.basename(input_file)
    output_size = os.path.getsize(export_path)
    input_size = os.path.getsize(input_file)
    output_size_mb = int(output_size) / (1024 * 1024)
    input_size_mb = int(input_size) / (1024 * 1024)
    size_difference = input_size - output_size
    percentage_difference = (size_difference / input_size) * 100
    print(f"{C1}{BOLD}\nFinished encoding {CF}{input_filename}{C3}\nInput size: {CI}{input_size_mb:.2f} MB\n{C3}Output size: {CI}{output_size_mb:.2f} MB\n{C3}size difference: {CI}{percentage_difference:.2f}%.{RESET}")
    transcode_number = transcode_number + 1
    transcoded_files.add(input_file)
    transcode_queue.remove(input_file)

def traverse(root_dir, filter_bitrate, target_bitrate, export_path, handbrake_exe, subfolder_regex, depth=0):
    global traversed_directories
    global transcode_queue
    supported_extensions = [".mp4", ".mkv", ".avi", ".mpg", ".ts", ".mxf", ".gxf", ".lxf", ".wmv", ".flv", ".mov", ".mp3"]
    root_dir = os.path.normpath(root_dir)
    if not os.path.isdir(root_dir):
        print(f"{CE}Error: {CF}{root_dir}{CE} is not a valid directory.{RESET}")
        sys.exit(1)
    if traversed_directories is None:
        traversed_directories = set()
    full_path = os.path.abspath(root_dir)
    if full_path in traversed_directories:
        print(f"{C2}Previously Traversed {CF}{root_dir}{C2} - Skipping.{RESET}")
        return
    print(f"{C2}Traversing {CF}{root_dir}{C2}...{RESET}")
    for item in os.listdir(full_path):
        if item.startswith('.'):
            continue
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            if depth > 0 or subfolder_regex is None or re.match(subfolder_regex, item):
                yield from traverse(item_path, filter_bitrate, target_bitrate, export_path, handbrake_exe, subfolder_regex, depth=depth+1)
        elif os.path.isfile(item_path):
            ext = os.path.splitext(item)[1]
            if ext.lower() not in supported_extensions:
                continue
            bitrate = get_bitrate(item_path)
            if bitrate is not None and bitrate > filter_bitrate * 1000000:
                size = os.path.getsize(item_path) / (1024 * 1024)
                duration_hours, duration_minutes, duration_seconds = get_duration_ffprobe(item_path)
                if len(item) > 65 + 5:
                    itemname = item[:65] + '...' + item[-5:]
                else:
                    itemname = item
                print(f"{C1}Found: {CF}{itemname} {CI}({duration_hours:.0f}h {duration_minutes:.0f}m {duration_seconds:.0f}s, {size:.2f}MB, {bitrate/1000000:.2f} Mbps)\n{RESET}", end='')
                transcode_queue.add(item_path)
                yield (item_path, bitrate)
    traversed_directories.add(full_path)

def save_transcode_queue():
    global traversed_directories
    global transcoded_files
    global transcode_queue
    file_name = 'transcode_queue.json'
    print(f"{C1}Saving progress...{RESET}")
    data = {
        "traversed_directories": list(traversed_directories),
        "transcode_queue": list(transcode_queue),
        "transcoded_files": list(transcoded_files),
    }
    with open(file_name, "w+") as file:
        json.dump(data, file)
    print(f"{CI}Progress saved. Exiting...{RESET}")
    sys.exit(0)

def handle_keyboard_interrupt():
    global traversed_directories
    global number_of_skipped_items
    global transcode_queue
    try:
        print(f"{CW}\nInterrupt detected. What would you like to do?\nTranscode queue contains{CI} {len(transcode_queue)+len(transcoded_files)}{CW} item(s).\n({CI}{len(transcoded_files)-number_of_skipped_items}{CW} files already transcoded).\n({CI}{number_of_skipped_items}{CW} file(s) skipped).\n1. Save progress and exit\n2. Start transcoding now{RESET}")
        choice = input(f"{CI}Enter your choice (1 or 2):\n(or 'delete' to reset queues){RESET}")
        if choice == "2":
            print(f"{C1}Starting transcoding...{RESET}")
            process_transcode_queue(preconfirm = True)
            return
        elif choice == '1':
            save_transcode_queue()
            print()
        elif choice == 'delete':
            if os.path.exists("transcode_queue.json"):    
                os.remove("transcode_queue.json")
                print(f"{CW}Queue has been deleted{RESET}")
                sys.exit(0)
            else:
                print(f"{CW}No Queue found. Exiting...{RESET}")
                sys.exit(0)
        else:
            print(f"{CE}Invalid choice. Please try again.{RESET}")
            handle_keyboard_interrupt()
    except KeyboardInterrupt:
            save_transcode_queue()
            sys.exit(0)

def process_transcode_queue(preconfirm=False):
    global transcode_queue
    global default_handbrake_exe
    global preset_file
    global starting_transcode_queue_length
    total_bitrate = 0
    if not transcode_queue:
        print(f'{CW}No files were found.{RESET}')
        return False
    print(f"{CI}Files in transcode queue:{RESET}")
    for path in transcode_queue:
        bitrate = get_bitrate(path)
        itemname = os.path.basename(path)
        if len(itemname) > 65 + 5:
            itemname = itemname[:65] + '...' + path[-5:]
        else:
            itemname = itemname
        print(f"{CF}{itemname} {CI}({bitrate/1000000:.2f} Mbps){RESET}")
        if bitrate is not None:
            total_bitrate += bitrate
    total_files = len(transcode_queue)
    average_bitrate = total_bitrate / total_files
    if preconfirm:
        confirm = 'yes'
    else:
        print(f'{C3}Found {CI}{total_files}{C3} file(s) with an average bitrate{C3} of {CI}{average_bitrate/1000000:.2f} Mbps{C3}.\nStart the transcode queue? ({C2}y{C3}es, {C2}n{C3}o, {C2}q{C3}uit, {C2}s{C3}ave){RESET}')
        confirm = input().lower()
    if confirm == 'yes' or confirm == 'y':
        print(f'{C3}Starting transcode process{RESET}')
        for file in set(transcode_queue):
            o = get_output_file(file, args.export_path)
            if o == 'null':
                print(f"{CI}Removing {CF}{file}{CI} from transcode queue.{RESET}")
                starting_transcode_queue_length -= 1
                transcode_queue.remove(file)
            else:
                transcode(file, o, target_bitrate=args.target_bitrate)
        print(f"{C1}Transcoding done.{RESET}")
        if os.path.exists("transcode_queue.json"):
            os.remove("transcode_queue.json")
        return process_complete()
    elif confirm == 'save' or confirm == 's':
        save_transcode_queue()
        print(f'{C3}Transcode queue saved for later.{RESET}')
        return False
    elif confirm == 'quit' or confirm == 'q':
        print(f'{CW}quitting without saving{RESET}')
        sys.exit(0)
    elif confirm =='n' or confirm =='no':
        return False
    else:
        print(f"{CE}{confirm} Is an Invalid Input{RESET}")
        return process_transcode_queue()

def transcode_queue_found():
    global transcode_queue
    global traversed_directories
    global transcoded_files
    with open("transcode_queue.json", "r") as file:
        data = json.load(file)
        transcode_queue = set(data["transcode_queue"])
        if "traversed_directories" in data:
            traversed_directories = set(data["traversed_directories"])
        else:
            traversed_directories = set()
        if "transcoded_files" in data:
            transcoded_files = set(data["transcoded_files"])
        else: 
            transcoded_files = set()
        if transcode_queue:
            r = process_transcode_queue()
            if r == True:
                print(f"{C1}Transcode Completed Successfully{RESET}")
            elif r == False:
                return
            else:
                print(f"{CE}uncaught exception{RESET}")
                sys.exit(0)

def process_complete():
    global transcoded_files
    total_original_size = 0
    total_output_size = 0
    try:    
        for file in transcoded_files:
            original_size = os.path.getsize(file)
            total_original_size += original_size
            output_file = get_output_file(file, args.export_path)
            output_size = os.path.getsize(output_file)
            total_output_size += output_size
        size_difference = total_original_size - total_output_size
        percentage_difference = (size_difference / total_original_size) * 100
        print(f'{C1}Done. Total original size: {total_original_size / (1024 * 1024):.2f} MB, total output size: {total_output_size / (1024 * 1024):.2f} MB, Pecentage decreased by: {percentage_difference:.2f}%.{RESET}')
        sys.exit(0)
    except:
        print(f'{C1}done{RESET}')
        sys.exit(0)

def continue_traversal():
    global transcode_queue
    for file in traverse(args.import_path, args.filter_bitrate, args.target_bitrate, args.export_path, args.handbrake_exe, args.subfolder_regex):
        transcode_queue.add(file[0])
    print(f"{C2}Traversal Complete{RESET}")
    start_transcoding = process_transcode_queue()
    if start_transcoding:
        return
    else:
        sys.exit(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Transcode videos with a bitrate greater than the specified threshold.', add_help=False)
    parser.add_argument('import_path', type=str, help='The path to the directory to import files from.')
    parser.add_argument('-f', '--filter-bitrate', type=int, default=10, help='The minimum bitrate of the files to transcode in Mbps. (default: 10)')
    parser.add_argument('-e', '--export-path', type=str, default=os.getcwd(), help='The path to the directory to export transcoded files to. (default: current working directory)')
    parser.add_argument('-t', '--target-bitrate', type=int, default=5, help='The target bitrate for the transcoded files in Mbps. (default: 5)')
    parser.add_argument('-F', '--flatten', action='store_true', help='Transcoded files will be placed in the export directory without creating a subfolder structure.')
    parser.add_argument('-H', '--handbrake-exe', type=str, help='The path to the HandBrakeCLI executable. (default: "HandBrakeCLI.exe")')
    parser.add_argument('-m', '--ffmpeg-exe', type=str, default=get_bitrate_executable, help='The path to the ffmpeg executable.')
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit.')
    parser.add_argument('-p', '--preset', type=str, help='The path to the HandBrakeCLI preset file. (overrules other quality arguments)')
    parser.add_argument('-s', '--subfolder-regex', type=str, help='Only process subfolders whose names match this regular expression.')
    args = parser.parse_args()
    preset_file = args.preset

    print(f'''{C1}
  __________  ___    _   _______ __________  ____  __________  ____ 
 /_  __/ __ \/   |  / | / / ___// ____/ __ \/ __ \/ ____/ __ \/ __ \\
  / / / /_/ / /| | /  |/ /\__ \/ /   / / / / / / / __/ / /_/ / /_/ /
 / / / _, _/ ___ |/ /|  /___/ / /___/ /_/ / /_/ / /___/ _, _/ _, _/ 
/_/ /_/ |_/_/  |_/_/ |_//____/\____/\____/_____/_____/_/ |_/_/ |_|  
                {C2}{ITALIC}Automate and Optimize{RESET}
    ''' 
    )
    try:
        if os.path.exists("transcode_queue.json"):
            print(f"{C2}previous run found - restoring...{RESET}")
            transcode_queue_found()
            print(f"{C2}Continuing Traversal...{RESET}")
        else:
            continue_traversal()
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
else:
    BOLD=ITALIC=UNDERLINE=RED=GREEN=YELLOW=MAGENTA=CYAN=BLACK=BLUE=WHITE=BLINK_SLOW=BLINK_FAST = "\033[0m"
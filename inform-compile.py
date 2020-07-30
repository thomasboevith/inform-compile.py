#!/usr/bin/python
import base64
import chardet
import docopt
import hashlib
import humanize
import logging
import os
import re
import sys
import tempfile
import time
import subprocess

version = '0.4'

__doc__ = """inform-compile.py {version} --- Compilation of Inform source to story files
Usage:
  {filename} --informbin=<name> --tmpdir=<name> [--devstage=<name>] [--dev|--release]
             [--language=<name>] [--librarypaths=<name>]
             [--unicode] [--outdirectory=<name>] [--storyfileprefix=<name>]
             [--storyfilesuffix=<name>] [--nostorysuffix]
             [--storyfileversion=<num>] [--writejs] [--force]
             [-v ...] <infiles>...
  {filename} (-h | --help)
  {filename} --version

Options:
  --devstage=<name>         Software development stage (development, release)
                                                            [default: release].
  --dev -d                  Short option for setting --devstage=development.
  --release                 Short option for setting --devstage=release.
  --language=<name>         Language of source code. (English/Danish)
                                                            [default: English].
  --informbin=<name>        Inform binary to use for compilation.
  --tmpdir=<name>           Path to directory for temporary files.
  --librarypaths=<name>     Library path(s) (comma-separated if more than one).
  --storyfileversion=<num>  Version of story file [default: 5].
                            Default is version-5 (Advanced) story file,
                            see http://inform-fiction.org/manual/html/s45.html
  --unicode -u              Source file is in unicode encoding.
                                                              [default: false].
  --outdirectory=<name>     Output directory for story files.
                                              (default is same as source file).
  --storyfileprefix=<name>  Prefix for story files.
  --storyfilesuffix=<name>  Suffix for story files
                                             (default is release_serialnumber).
  --nostorysuffix -n        Set suffix to empty string.
  --writejs                 Also write javascript version (encoding to Base64).
  --force -f                Force overwriting of story files.
  --help -h                 Show this screen.
  --version                 Show version.
  -v                        Print info (-vv for printing lots of info (debug)).

Copyright (C) 2020 Thomas Boevith

License: GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it. There is NO
WARRANTY, to the extent permitted by law.
""".format(filename=os.path.basename(__file__), version=version)


def md5(filename):
    hash = hashlib.md5()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash.update(chunk)
    return hash.hexdigest()


def filesize(filename):
    return humanize.naturalsize(os.path.getsize(filename), gnu=True)


def getmetadata(filename):
    metadata = {}
    keys = []
    pattern = re.compile('^! \w+:')
    storyfile_releasenumber = []
    storyfile_serialnumber = []
    releasenumber_pattern = re.compile('^Release \d+')
    serialnumber_pattern = re.compile('^Serial "\d+"')
    number_pattern = re.compile('\d+')
    rawdata = open(filename, 'rb').read()
    result = chardet.detect(rawdata)
    charenc = result['encoding']
    for line in open(filename, encoding=charenc):
        if re.findall(pattern, line):
            fieldname, value = line.split(':')
            fieldname = fieldname.split(' ')[1:][0].lower()
            metadata[fieldname] = value.rstrip('\n').strip()
            keys.append(fieldname)
        elif re.findall(releasenumber_pattern, line):
            releasenumber = re.findall(releasenumber_pattern, line)[0]
            metadata['release'] = releasenumber.split()[1]
            keys.append('release')
        elif re.findall(serialnumber_pattern, line):
            serialnumber = re.findall(serialnumber_pattern, line)[0]
            metadata['serial'] = serialnumber.split()[1][1:-1]
            keys.append('serial')
        elif line == '\n':
            break

    return metadata, keys

if __name__ == '__main__':
    start_time = time.time()
    args = docopt.docopt(__doc__, version=str(version))

    log = logging.getLogger(os.path.basename(__file__))
    formatstr = '%(asctime)-15s %(name)-17s %(levelname)-5s %(message)s'
    if args['-v'] >= 2:
        logging.basicConfig(level=logging.DEBUG, format=formatstr)
    elif args['-v'] == 1:
        logging.basicConfig(level=logging.INFO, format=formatstr)
    else:
        logging.basicConfig(level=logging.WARNING, format=formatstr)

    if args['--dev']:
        args['--devstage'] = 'development'

    log.debug('%s started' % os.path.basename(__file__))
    log.debug('docopt args=%s' % args)

    if not os.path.exists(args['--informbin']):
        log.error('Inform binary not found: %s' % args['--informbin'])
        sys.exit(1)
    else:
        command = [args['--informbin']]
    
    if not os.path.exists(args['--tmpdir']):
        log.error('Temporary directory not found: %s' % args['--tmpdir'])
        sys.exit(1)
    
    for infile in args['<infiles>']:
        log.info('Processing infile: %s' % infile)
        infiledirname, infilename = os.path.split(infile)
        infilebasename, infileextension = os.path.splitext(infilename)
        if infiledirname == '':
            infiledirname = './'

        metadata, keys = getmetadata(infile)

        if not args['--outdirectory']:
            args['--outdirectory'] = infiledirname
            log.info('Output directory --outdirectory not specified. ' +
                     'Using same directory as source file: %s' %
                     args['--outdirectory'])

        if not os.path.isdir(args['--outdirectory']):
            log.error('Output directory not found: %s'
                      % args['--outdirectory'])
            sys.exit(1)

        if args['--outdirectory'][-1] != '/':  # Ensure directory ends in /
            args['--outdirectory'] += '/'

        if not args['--storyfileprefix']:
            args['--storyfileprefix'] = ''

        if not args['--storyfilesuffix']:
            if 'release' in metadata.keys():
                storyfile_releasenumber = metadata['release']
            else:
                storyfile_releasenumber = '1'  # Default release number

            if 'serial' in metadata.keys():
                storyfile_serialnumber = metadata['serial']
            else:
                # Default serial number
                storyfile_serialnumber = time.strftime('%y%m%d')

            args['--storyfilesuffix'] = '_' + storyfile_releasenumber + '_' \
                                        + storyfile_serialnumber

        if args['--nostorysuffix']:
            args['--storyfilesuffix'] = ''

        storyfilename = args['--outdirectory'] + args['--storyfileprefix'] \
                        + infilebasename + args['--storyfilesuffix'] + '.z' \
                        + str(args['--storyfileversion'])

        if not os.path.isfile(infile):
            log.warning('Infile not found: %s ... skipping it' % infile)
            continue
        elif infileextension != '.inf':
            log.warning('Possibly not inform source code: %s ... skipping it'
                        % infile)
            continue

        if os.path.isfile(storyfilename) and not args['--force']:
            log.warning('Storyfilename already exists: %s ... skipping (use --force or -f to overwrite)' % infile)
            continue

        log.info('Building command string')

        if args['--unicode']:
            command.append('-Cu')

        if args['--devstage'] == 'release':
            command.append('-~S')
            # ^^ For RELEASE_VERSION use -~S: De-activate strict mode (~S)
            # (it is on by default)
        elif args['--devstage'] == 'development':
            command.append('-SDX')
            # ^^ For DEVELOPMENT_VERSION use -SDX : strict mode (S),
            # debugger (D) and infix debugger (X)
        if args['-v'] >= 1:  # Show compilation statistics (-s)
            command.append('-s')

        if 'sprog' in metadata.keys():
            args['--language'] = metadata['sprog'].lower()

        if (args['--language'].lower() == 'danish') \
               or (args['--language'].lower() == 'dansk'):
            command.append('+language_name=Danish')

        # Append source file dir to library paths
        if args['--librarypaths']:
          librarypaths = '+'+args['--librarypaths']+','+infiledirname
          command.append(librarypaths)

        command.append(tmpdir)
        command.append(infile)
        command.append(storyfilename)
        log.info('Compiling infile with command: %s' % ' '.join(command))
        try:
            returncode = subprocess.call(' '.join(command), shell=True)
        except Exception as ex:
            log.exception('Exception: %s' % ex)
            sys.exit(1)

        if returncode != 0:
            log.error('Compilation of file: %s unsuccessful' % infile)
            sys.exit(1)
        else:
            log.info('Compilation of file: %s successful' % infile)
            log.info('Wrote storyfile: %s' % (storyfilename))
            storyfile_md5sum = md5(storyfilename)
            log.info('Storyfile md5sum: %s' % storyfile_md5sum)
            storyfile_size = filesize(storyfilename)
            log.info('Storyfile size: %s' % storyfile_size)
            if not os.path.isfile(storyfilename):
                log.error(' but storyfile: %s not found' % storyfilename)
                sys.exit(1)

        # FIXME TODO write readme.txt with metadata?

        if args['--writejs']:
            log.info('Base64 encoding of the storyfile for ' +
                     ' parchment (javascript)')
            # Based on code from parchment, zcode2js.py
            contents = open(storyfilename, "rb").read()
            encoded_contents = base64.b64encode(contents)
            base64storyfilename = storyfilename + '.js'
            f = open(base64storyfilename, 'w+')
            f.write("processBase64Zcode('%s');" % encoded_contents)
            f.close()
            log.info('Wrote base64 encoded storyfile: %s'
                     % (base64storyfilename))
            base64storyfile_md5sum = md5(base64storyfilename)
            log.info('Base64 encoded storyfile md5sum: %s'
                     % base64storyfile_md5sum)
            base64storyfile_size = filesize(base64storyfilename)
            log.info('Base64 encoded storyfile size: %s'
                     % base64storyfile_size)

    # FIXME TODO Symbolic link to newest?

    log.debug('Processing time={0:.2f} s'.format(time.time() - start_time))
    log.debug('%s ended' % os.path.basename(__file__))

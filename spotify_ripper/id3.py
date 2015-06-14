# -*- coding: utf8 -*-

from __future__ import unicode_literals

from colorama import Fore, Style
from mutagen import mp3, id3, flac
from stat import ST_SIZE
from spotify_ripper.utils import *
import os, sys
import requests

def set_id3_and_cover(args, mp3_file, track):
    # ensure everything is loaded still
    if not track.is_loaded: track.load()
    if not track.album.is_loaded: track.album.load()
    album_browser = track.album.browse()
    album_browser.load()

    # calculate num of tracks on disc and num of dics
    num_discs = 0
    num_tracks = 0
    for track_browse in album_browser.tracks:
        if track_browse.disc == track.disc and track_browse.index > track.index:
            num_tracks = track_browse.index
        if track_browse.disc > num_discs:
            num_discs = track_browse.disc

    # try to get genres from Spotify's Web API
    genres = None
    if args.genres is not None:
        item = track.artists[0] if args.genres[0] == "artist" else track.album
        uri_tokens = item.link.uri.split(':')
        if len(uri_tokens) == 3:
            url = 'https://api.spotify.com/v1/' + args.genres[0] + 's/' + uri_tokens[2]
            print(Fore.GREEN + "Attempting to retrieve genres from Spotify's Web API" + Fore.RESET)
            print(Fore.CYAN + url + Fore.RESET)
            req = requests.get(url)
            if req.status_code == 200:
                try:
                    resp_json = req.json()
                    genres = resp_json["genres"]
                except KeyError as e:
                    pass
            else:
                print(Fore.YELLOW + "URL returned non-200 HTTP code: " + str(req.status_code) + Fore.RESET)

    # use mutagen to update id3v2 tags
    try:
        audio = None
        on_error = 'replace' if args.ascii_path_only else 'ignore'
        album = to_ascii(args, track.album.name, on_error)
        artist = to_ascii(args, track.artists[0].name, on_error)
        title = to_ascii(args, track.name, on_error)
        if genres is not None and genres:
            genres_ascii = [to_ascii(args, genre) for genre in genres]

        # cover art image
        image = track.album.cover()

        def id3_to_ascii(_str, _str_ascii):
            return _str if args.ascii_path_only else _str_ascii

        def idx_of_total_str(_idx, _total):
            if _total > 0:
                return "%d/%d" % (_idx, _total)
            else:
                return "%d" % (_idx)

        def set_id3_tags(audio):
            # add ID3 tag if it doesn't exist
            audio.add_tags()

            if image is not None:
                image.load()
                audio.tags.add(
                    id3.APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Front Cover',
                        data=image.data
                    )
                )

            if album is not None: audio.tags.add(id3.TALB(text=[id3_to_ascii(track.album.name, album)], encoding=3))
            audio.tags.add(id3.TIT2(text=[id3_to_ascii(track.name, title)], encoding=3))
            audio.tags.add(id3.TPE1(text=[id3_to_ascii(track.artists[0].name, artist)], encoding=3))
            audio.tags.add(id3.TDRL(text=[str(track.album.year)], encoding=3))
            audio.tags.add(id3.TPOS(text=[idx_of_total_str(track.disc, num_discs)], encoding=3))
            audio.tags.add(id3.TRCK(text=[idx_of_total_str(track.index, num_tracks)], encoding=3))
            if genres is not None and genres:
                tcon_tag = id3.TCON(encoding=3)
                tcon_tag.genres = genres if args.ascii_path_only else genres_ascii
                audio.tags.add(tcon_tag)

            audio.save()

        def set_flac_metadata(audio):
            # add Vorbis comment block if it doesn't exist
            if audio.tags is None:
                audio.add_tags()

            if image is not None:
                image.load()
                pic = flac.Picture()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc="Front Cover"
                pic.data = image.data
                audio.add_picture(pic)

            if album is not None: audio.tags["ALBUM"] = id3_to_ascii(track.album.name, album)
            audio.tags["TITLE"] = id3_to_ascii(track.name, title)
            audio.tags["ARTIST"] = id3_to_ascii(track.artists[0].name, artist)
            audio.tags["YEAR"] = str(track.album.year)
            audio.tags["DISCNUMBER"] = str(track.disc)
            audio.tags["DISCTOTAL"] = str(num_discs)
            audio.tags["TRACKNUMBER"] = str(track.index)
            audio.tags["TRACKTOTAL"] = str(num_tracks)

            if genres is not None and genres:
                _genres = genres if args.ascii_path_only else genres_ascii
                audio.tags["GENRE"] = ", ".join(_genres)

            audio.save()

        if args.flac:
            audio = flac.FLAC(mp3_file)
            set_flac_metadata(audio)
        else:
            audio = mp3.MP3(mp3_file, ID3=id3.ID3)
            set_id3_tags(audio)

        def bit_rate_str(bit_rate):
           brs = "%d kb/s" % bit_rate
           if not args.cbr:
              brs = "~" + brs
           return brs

        def mode_str(mode):
            modes = ["Stereo", "Joint Stereo", "Dual Channel", "Mono"]
            if mode < len(modes):
                return modes[mode]
            else:
                return ""

        # log id3 tags
        print(Fore.GREEN + Style.BRIGHT + os.path.basename(mp3_file) + Style.NORMAL + "\t[ " + format_size(os.stat(mp3_file)[ST_SIZE]) + " ]" + Fore.RESET)
        print("-" * 79)
        print(Fore.YELLOW + "Setting artist: " + artist + Fore.RESET)
        if album is not None: print(Fore.YELLOW + "Setting album: " + album + Fore.RESET)
        print(Fore.YELLOW + "Setting title: " + title + Fore.RESET)
        print(Fore.YELLOW + "Setting track info: (" + str(track.index) + ", " + str(num_tracks) + ")"  + Fore.RESET)
        print(Fore.YELLOW + "Setting disc info: (" + str(track.disc) + ", " + str(num_discs) + ")"  + Fore.RESET)
        print(Fore.YELLOW + "Setting release year: " + str(track.album.year) + Fore.RESET)
        if genres is not None and genres: print(Fore.YELLOW + "Setting genres: " + " / ".join(genres_ascii) + Fore.RESET)
        if image is not None: print(Fore.YELLOW + "Adding cover image" + Fore.RESET)
        if args.flac:
            bit_rate = (audio.info.bits_per_sample * audio.info.total_samples) / audio.info.length
            print("Time: " + format_time(audio.info.length) + "\tFree Lossless Audio Codec"+
                "\t[ " + bit_rate_str(bit_rate / 1000) + " @ " + str(audio.info.sample_rate) +
                " Hz - " + ("Stereo" if audio.info.channels == 2 else "Mono") + " ]")
            print("-" * 79)
            print(Fore.YELLOW + "Writing Vorbis comments - " + audio.tags.vendor + Fore.RESET)
            print("-" * 79)

        else:
            print("Time: " + format_time(audio.info.length) + "\tMPEG" + str(audio.info.version) +
                ", Layer " + ("I" * audio.info.layer) + "\t[ " + bit_rate_str(audio.info.bitrate / 1000) +
                " @ " + str(audio.info.sample_rate) + " Hz - " + mode_str(audio.info.mode) + " ]")
            print("-" * 79)
            id3_version = "v%d.%d" % (audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " + str(len(audio.tags.values())) + " frames")
            print(Fore.YELLOW + "Writing ID3 version " + id3_version + Fore.RESET)
            print("-" * 79)

    except id3.error:
        print(Fore.YELLOW + "Warning: exception while saving id3 tag: " + str(id3.error) + Fore.RESET)

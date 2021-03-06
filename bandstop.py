#!/usr/bin/env python3

import sys
if len(sys.argv) == 1:
    print("usage: ./bandstop.py <files>")
    sys.exit(1)

import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy import signal
from scipy.fftpack import fft, fftfreq
import argparse
from sound import Sound, DepthException
import re

plt.ion() # Make the plot interactive
# Allows us to update it in the code

FFT_SAMPLE_SIZE = 10000 # FFT sample size in milliseconds
FREQUENCY_MAXIMUM_DIFFERENTIATING_DIFFERENCE = 50 # Hz
FREQUENCY_BANDSTOP_MARGIN = 50 # Hz
FREQUENCY_MINIMUM_COUNT = 20 # this should be inversely proportional to FFT_SAMPLE_SIZE

DEBUG = True
SHOW_FFT = True

def gen_output_filename(filename):
    pattern = re.compile("\.[^.]+$")
    return pattern.sub("-out.wav", filename)

def process(filename):
    fs, snd = wavfile.read(filename)

    try:
        sndobj = Sound(fs, snd)

    except DepthException as e:
        print(e)
        print("Skipping...")
        return

    print("==== Information about {} ====".format(filename))
    print("Samples: {}".format(sndobj.samples))
    print("Channels: {}".format(sndobj.channels))
    print("Duration: {}".format(sndobj.duration))
    print("Depth: {}-bit".format(sndobj.depth))
    print("============================"+"="*len(filename))

    signals_to_save = np.array([], dtype=np.int64).reshape(sndobj.samples, 0)
    for c in range(sndobj.channels):
        print("Parsing channel {}".format(c))
        cleaned_signal = parse(snd.T[c], sndobj)
        signals_to_save = np.column_stack([signals_to_save, cleaned_signal])
        if DEBUG:
            print(signals_to_save)

    output_filename = gen_output_filename(filename)
    print("Saving to {}".format(output_filename))
    wavfile.write(output_filename, rate=sndobj.fs, data=signals_to_save)


def find_outstanding_frequencies(data, sndobj, points_per_sample):
    # THRESHOLD = 5000000
    diff_data = np.diff(data)
    low_band = points_per_sample//4 # Half of our divided version
    # Above this value are frequencies that are considered for removal

    num_outstanding = 3

    # Find the frequencies of highest difference
    low_ind = np.argpartition(diff_data[low_band:], -num_outstanding)[-num_outstanding:] + low_band
    # Find the frequencies of most negative difference
    high_ind = np.argpartition(-diff_data[low_band:], -num_outstanding)[-num_outstanding:] + low_band

    # Normalize
    low_ind = (low_ind * sndobj.fs)//points_per_sample
    high_ind = (high_ind * sndobj.fs)//points_per_sample

    # np.where(data[high_ind] > THRESHOLD * points_per_sample, high_ind, 0)

    if DEBUG:
        sys.stdout.write("h indices: ")
        print(high_ind)
        sys.stdout.write("l indeces: ")
        print(low_ind)
        # print(fs/points_per_sample * data[high_ind])

        # Convert back to graph units
        if SHOW_FFT:
            for x in (high_ind * points_per_sample)//sndobj.fs:
                plt.axvline(x=x, color='b')
            for x in (low_ind * points_per_sample)//sndobj.fs:
                plt.axvline(x=x, color='g')

    ret = []
    for ind1 in high_ind:
        for ind2 in low_ind:
            if abs(ind1 - ind2) < FREQUENCY_MAXIMUM_DIFFERENTIATING_DIFFERENCE:
                ret.append((ind1, ind2) if ind2 > ind1 else(ind2, ind1))

    return ret

def extract_bandstop_frequencies(cand):
    candidates = np.array(cand)
    candidates[:,1] += FREQUENCY_BANDSTOP_MARGIN
    candidates[:,0] -= FREQUENCY_BANDSTOP_MARGIN

    final = []
    for c in np.array(candidates):
        avg = (c[0] + c[1])/2
        placed = False
        for f in final:
            favg = (f["data"][0] + f["data"][1])/(2 * f["count"])
            if abs(avg - favg) < FREQUENCY_MAXIMUM_DIFFERENTIATING_DIFFERENCE:
                f["count"] += 1
                f["data"] += c
                placed = True
                break
        if placed: continue
        final.append({
            "data": c,
            "count": 1
        });

    ret = []
    if DEBUG:
        print(final)
    for f in final:
        if f["count"] > FREQUENCY_MINIMUM_COUNT:
            ret.append(f["data"]/f["count"])

    return ret

def rms(a):
    b = np.array(a, dtype=np.int64)
    return np.sqrt(np.mean(b ** 2))

def bandstop(frequencies, sound_data, sndobj):
    for ft in frequencies:
        if DEBUG:
            print("Old RMS: {}".format(rms(sound_data)))
        center = (ft[0] + ft[1])/2
        w0 = center/(sndobj.fs/2)
        dist = abs(ft[0] - ft[1])
        q = 2 * center/dist
        if(dist < 10):
            dist = 10
        if DEBUG:
            print("w0: {}, Q: {}".format(w0, 2 * center/dist))
        fa, fb = signal.iirnotch(w0, 2 * center/dist) # Bandstop filters
        sound_data = signal.filtfilt(fa, fb, sound_data)
        if DEBUG:
            print("New RMS: {}".format(rms(sound_data)))
    return sound_data # Cleaned



def parse(sound_data, sndobj):
    print("Parsing sound data: RMS: {}".format(rms(sound_data)))
    points_per_sample = FFT_SAMPLE_SIZE*sndobj.fs//1000
    # frequency_data = fftfreq(points_per_sample, FFT_SAMPLE_SIZE/1000)*points_per_sample * FFT_SAMPLE_SIZE/1000
    # frequency_conversion_ratio = fs/points_per_sample
    candidate_frequencies = []
    for i in range(0, sndobj.samples, points_per_sample):
        # FFT data
        fft_data = fft(sound_data[i:(i+points_per_sample)])
        real_length = len(fft_data)//2
        # We only care about the first half; the other half is the same
        real_data = abs(fft_data[:(real_length-1)])

        if SHOW_FFT:
            # Plot the data as a frequency spectrum
            plt.plot(real_data,'r')
            plt.show()
            plt.pause(0.2)
            plt.clf()

        sample_freqs = find_outstanding_frequencies(real_data, sndobj, points_per_sample)
        # Tuple of high and low bands
        candidate_frequencies += sample_freqs

    bandstop_frequencies = extract_bandstop_frequencies(candidate_frequencies)
    if not bandstop_frequencies:
        print("No frequencies to remove...")
        return sound_data

    print("Removing the following frequencies:")
    for ft in bandstop_frequencies:
        print("{}-{}Hz".format(*ft))

    cleaned = bandstop(bandstop_frequencies, sound_data, sndobj)
    return cleaned

for filename in sys.argv[1:]:
    process(filename)

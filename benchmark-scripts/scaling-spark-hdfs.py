#!/usr/bin/env python3
###########################################################################
##
## Copyright (c) 2014 Adobe Systems Incorporated. All rights reserved.
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
## http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.
##
###########################################################################

import argparse
from urllib.request import urlopen
import yaml
import statistics
import os
import sys
import time
import re
from subprocess import Popen, PIPE
import traceback

import bench_base

import matplotlib.pyplot as plt
from matplotlib import rc
rc('font',**{'family':'sans-serif','sans-serif':['Helvetica']})
rc('text', usetex=True)

import seaborn as sns
sns.set(style='ticks', palette='Set2')

scHost = "localhost"
scPort = 8605

def runScalingExperiment(queries, data_dir):
  print("Running scaling experiment.")
  memoryPerWorker = "21g"
  timesToRun = 4
  tps = 1500000
  allNodes = [6,5,4,3]
  cache = True

  outFilePath = data_dir + "/scaling/scaling.yaml"
  if os.path.isfile(outFilePath):
    with open(outFilePath, "r") as f: data = yaml.load(f)
  else: data = {}

  for nodes in allNodes:
    cores = nodes*24-1
    if nodes not in data: data[nodes] = {'dataLoad': [], 'execution': {}}
    if len(data[nodes]['dataLoad']) < timesToRun or \
        len(data[nodes]['execution']) < len(queries):
      input("Please ensure {} Spark and HDFS nodes are running and press any key to continue.".format(nodes))

    while len(data[nodes]['dataLoad']) < timesToRun or \
        len(data[nodes]['execution']) < len(queries):
      try:
        bench_base.restartServers()
        bench_base.restartSparkContext(memoryPerWorker, cores)
        while len(data[nodes]['dataLoad']) < timesToRun:
          result = bench_base.getDataLoadTime()
          data[nodes]['dataLoad'].append(
            result[1]['TimeMillis'] - result[0]['TimeMillis']
          )
        with open(outFilePath, "w") as f:
          f.write(yaml.dump(data, indent=2, default_flow_style=False))
        for query in queries:
          exeData = data[nodes]['execution']
          if query not in exeData: exeData[query] = []
          if len(exeData[query]) >= timesToRun:
            print("  Already profiled for nodes = " + str(nodes) + ", skipping.")
            continue
          while len(exeData[query]) < timesToRun:
            # Load the data into cache.
            if cache:
              bench_base.runQuery(query,"2014-01-01","2014-01-07",cache,tps)
            while len(exeData[query]) < timesToRun:
              result = bench_base.runQuery(
                query,"2014-01-01","2014-01-07",cache,tps
              )
              exeData[query].append(
                result[2]['TimeMillis'] - result[0]['TimeMillis']
              )
            with open(outFilePath, "w") as f:
              f.write(yaml.dump(data, indent=2, default_flow_style=False))
      except KeyboardInterrupt: sys.exit(-1)
      except Exception:
        print("Exception occurred, retrying.")
        traceback.print_exc()
        if not cache: data[cache] = []
        pass
  return data

def plotDataLoadTimes(data, data_dir):
  def getStats(data):
    y = []; err = []; names = []; shortNames = []
    i = 0
    sortedKeys = sorted(data)
    for numWorkers in sortedKeys:
      y.append(statistics.mean(data[numWorkers]['dataLoad']))
      err.append(statistics.stdev(data[numWorkers]['dataLoad']))
      i+=1
    return (y,err)

  bar_width = 0.35
  fig = plt.figure()
  ax = plt.subplot(111)
  plt.title("Loading Data")
  plt.ylabel("Time (ms)")
  plt.xlabel("Number of Spark and HDFS Workers")
  (y,err) = getStats(data)
  ind_c = range(len(y))
  ind_n = [x+bar_width for x in ind_c]
  tick_idx = [x+bar_width*3/2 for x in ind_c]
  bar_c = ax.bar(ind_n, y, bar_width, color='white', yerr=err, ecolor="#363636")
  # bar_n = ax.bar(ind_n, y_nocache, bar_width, color='white', edgecolor="black",
  #     hatch="/", yerr=err_nocache, ecolor="#363636")
  # plt.errorbar(x, y, yerr=err, marker='.', color='black',ecolor="gray")
  # plt.axis([0, 1.02*maxX, 0, 1.02*(maxY+max(err))])
  # plt.grid()
  ax.set_xticks(tick_idx)
  ax.set_xticklabels(sorted(data))
  # leg = ax.legend((bar_c), ("Caching", "No Caching"),
  #   fancybox=True, loc="upper left")
  # leg.get_frame().set_alpha(0.5)

  def autolabel(rects):
    # attach some text labels
    for rect in rects:
      height = rect.get_height()
      ax.text(rect.get_x()+rect.get_width(), height+10, '%d'%int(height),
        ha='right', va='bottom', size=9)
  autolabel(bar_c)

  plt.savefig(data_dir + "/scaling/dataLoad.pdf")
  plt.savefig(data_dir + "/scaling/dataLoad.png")
  plt.clf()

def printSpeedups(data, data_dir):
  def getStats(data):
    y = {}; err = {}
    i = 0
    sortedKeys = sorted(data)
    for numWorkers in sortedKeys:
      y[numWorkers] = []; err[numWorkers] = []
      for q in queries:
        y[numWorkers].append(statistics.mean(data[numWorkers]['execution'][q]))
        err[numWorkers].append(statistics.stdev(data[numWorkers]['execution'][q]))
      i+=1
    return (y,err)
  (y,err) = getStats(data)

  # Print stats.
  def two(s): return "{:.2f}".format(s)
  print(" & ".join([str(numWorkers) for numWorkers in sorted(y)])+r" \\ \hline")
  i = 0
  fig = plt.figure()
  ax = fig.add_subplot(111)
  labels = []
  for q in queries:
    labels.append(shortNames[i])
    row = [shortNames[i]]
    plot_y = []; plot_err = []
    for numWorkers in sorted(y):
      row.append(two(y[numWorkers][i]/1000))
      row.append(two(err[numWorkers][i]/1000))
      plot_y.append(y[numWorkers][i]/1000)
      plot_err.append(err[numWorkers][i]/1000)
    init_y = plot_y[0]
    for j in range(len(plot_y)):
      plot_y[j] = plot_y[j]/init_y
      plot_err[j] = plot_err[j]/init_y
    ax.plot(sorted(y),plot_y)
    ax.scatter(sorted(y),plot_y,marker='o',c='k',s=[x*400 for x in plot_err])
    print(" & ".join(row) + r" \\")
    i += 1

  box = ax.get_position()
  ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
  ax.legend(labels,loc='center left',bbox_to_anchor=(1,0.5))
  ax.set_xlabel("Number of Spark and HDFS Workers")
  ax.set_ylabel("Normalized Execution Time")
  plt.xticks((3,4,5,6))
  plt.savefig(data_dir+"/scaling/scalingWorkers.pdf")
  plt.savefig(data_dir+"/scaling/scalingWorkers.png")

parser = argparse.ArgumentParser()
parser.add_argument("--collect-data", dest="collect", action="store_true")
parser.add_argument("--create-plots", dest="plot", action="store_true")
parser.add_argument("--data-dir", dest="data_dir", type=str, default=".")
args = parser.parse_args()

queries = [
  "Pageviews",
  "Revenue",
  "RevenueFromTopReferringDomains",
  "RevenueFromTopReferringDomainsFirstVisitGoogle",
  "TopPages",
  "TopPagesByBrowser",
  "TopPagesByPreviousTopPages",
  "TopReferringDomains"
]
shortNames = ["Q{}".format(x) for x in range(len(queries))]
if args.collect:
  if not os.path.isdir(args.data_dir + "/scaling"):
    os.makedirs(args.data_dir + "/scaling")
  runScalingExperiment(queries, args.data_dir)

if args.plot:
  data = {}
  with open(args.data_dir+"/scaling/scaling.yaml", "r") as f:
    data.update(yaml.load(f))

  print(data)
  plotDataLoadTimes(data, args.data_dir)
  printSpeedups(data, args.data_dir)
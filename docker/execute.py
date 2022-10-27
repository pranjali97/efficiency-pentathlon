#!/usr/bin/env python
import time
import sys
import os
import subprocess
import signal
import docker
import time
import csv
import multiprocessing
from utils import get_num_instances
from utils import LOG_DIR
import pathlib


if __name__ == "__main__":
    cur_dir = os.getcwd()
    monitor_dir = pathlib.Path(__file__).parent.resolve()
    os.chdir(monitor_dir)
    print(os.getcwd())
    if not os.path.exists(LOG_DIR):
        os.mkdir(LOG_DIR)
    num_cpus = multiprocessing.cpu_count()
    client = docker.from_env()
    devnull = open("/dev/null", "w")
    container = client.containers.run(
        "test:latest",
        "python workspace/profile_cpu.py",
        name="test",
        privileged=True,
        tty=True,
        remove=True,
        volumes={
            f"{os.getcwd()}/workspace": {"bind": "/app/workspace", "mode": "rw"}
        },
        detach=True
    )
    output = container.attach(stdout=True, stream=True, logs=True, stderr=True)
    p_gpu = subprocess.Popen([f"{sys.executable}", "workspace/profile_gpu.py"], stdout=devnull, shell=False)
    p_docker = subprocess.Popen([f"sh", "docker_monitor.sh"], stdout=devnull, shell=False)

    print("Executing:", " ".join(sys.argv[1:]))
    os.chdir(cur_dir)
    start_time = time.time()
    os.system(" ".join(sys.argv[1:]))
    end_time = time.time()
    os.chdir(monitor_dir)
    os.kill(p_gpu.pid, signal.SIGTERM)
    if not p_gpu.poll():
        print("GPU monitor correctly halted")
    os.kill(p_docker.pid, signal.SIGTERM)
    if not p_docker.poll():
        print("Docker monitor correctly halted")
    container.kill("SIGTERM")

    gpu_energy, max_gpu_mem = 0, 0
    cpu_energy, mem_energy = 0, 0
    with open(f"{LOG_DIR}/gpu.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            gpu_energy = gpu_energy + float(row["energy"])
            max_gpu_mem = max_gpu_mem + float(row["max_mem"])
    with open("workspace/log/cpu.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            cpu_energy = cpu_energy + float(row["cpu_energy"])
            mem_energy = mem_energy + float(row["dram_energy"])
    with open(f"{LOG_DIR}/docker.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        cpu_util, mem_util, max_mem_util = 0, 0, 0
        num_rows = 1e-6
        for row in reader:
            num_rows += 1
            cpu_util = cpu_util + float(row["cpu_util"].strip("%")) / 100
            mem_util = mem_util + float(row["mem_util"].strip("%")) / 100
            max_mem_util = max(max_mem_util, mem_util)
        cpu_util = cpu_util / (num_rows) / num_cpus
        mem_util = mem_util / (num_rows)
    cpu_energy = cpu_energy * cpu_util
    mem_energy = mem_energy * mem_util
    total_memory = subprocess.getoutput("cat /proc/meminfo | grep MemTotal")  # in kB
    total_memory = float(total_memory.split()[1]) / 2 ** 20
    num_instances = get_num_instances("iwslt14ende")
    time_elapsed = end_time - start_time
    print(f"Time Elapsed: {time_elapsed:.3f} s") 
    print(f"Throughput: {num_instances / time_elapsed: .3f} instances/s")
    print(f"GPU Energy: {gpu_energy:.3f} W.s", end="; ")
    print(f"CPU Energy: {cpu_energy: .3f} W.s", end="; ")
    print(f"Memory Energy: {mem_energy: .3f} W.s", end="; ")
    print(f"Total Energy: {gpu_energy + cpu_energy + mem_energy: .3f} W.s")
    print(f"Max DRAM Memory Usage: {max_mem_util * total_memory: .3f} GiB")
    print(f"Max GPU Memory Usage: {max_gpu_mem: .3f} GiB")  # TODO: check with Qingqing why is this always zero
    
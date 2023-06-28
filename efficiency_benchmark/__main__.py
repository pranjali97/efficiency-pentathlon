import os
import sys
from typing import List, Optional, Tuple
import json
import click
from click_help_colors import HelpColorsCommand, HelpColorsGroup

from efficiency_benchmark.steps import (CalculateMetricsStep, LogOutputStep,
                                        PredictStep, TabulateMetricsStep)
from eb_gantry.__main__ import run as gantry_run
from efficiency_benchmark.tasks import TASKS
from efficiency_benchmark.tasks.efficiency_benchmark import EfficiencyBenchmarkWrapper
from efficiency_benchmark.tasks.efficiency_benchmark import EfficiencyBenchmarkHuggingfaceTask
from efficiency_benchmark.utils import parse_gpu_ids


_CLICK_GROUP_DEFAULTS = {
    "cls": HelpColorsGroup,
    "help_options_color": "green",
    "help_headers_color": "yellow",
    "context_settings": {"max_content_width": 115},
}

_CLICK_COMMAND_DEFAULTS = {
    "cls": HelpColorsCommand,
    "help_options_color": "green",
    "help_headers_color": "yellow",
    "context_settings": {"max_content_width": 115},
}


@click.group(**_CLICK_GROUP_DEFAULTS)
def main():
    pass


@main.command(**_CLICK_COMMAND_DEFAULTS)
@click.argument("cmd", nargs=-1)
@click.option(
    "-h",
    "--hf_dataset_args",
    type=str,
    nargs=1,
    help="""Args for Huggingface load_dataset.""",
    default=None
)
@click.option(
    "-t",
    "--task",
    type=str,
    nargs=1,
    help="""Tasks.""",
)
@click.option(
    "--split",
    type=str,
    help="""Split.""",
    default="test",
)
@click.option(
    "-s",
    "--scenario",
    type=str,
    default="fixed_batch",
    help="""Evaluation scenario [single_stream, fixed_batch, random_batch, offline].""",
)
@click.option(
    "-b",
    "--max_batch_size",
    type=int,
    default=32,
    help="""Maximum batch size.""",
)
@click.option(
    "-o",
    "--offline_dir",
    type=str,
    nargs=1,
    help="""Offline dir.""",
)
@click.option(
    "--output_dir",
    type=str,
    nargs=1,
    help="""Output folder.""",
)
@click.option(
    "-l",
    "--limit",
    type=int,
    default=-1,
    help="""Limit.""",
)
@click.option(
    "--gpus",
    type=str,
    help="""The IDs of the GPUs to use. Example: `--gpus 0,1`. If not specified, all GPUs will be profiled by default.""",
)
def run(
    cmd: Tuple[str, ...],
    task: Optional[str] = None,
    hf_dataset_args: Optional[str] = None,
    split: str = "test",
    scenario: str = "fixed_batch",
    max_batch_size: int = 32,
    offline_dir: str = f"{os.getcwd()}/datasets/efficiency-beenchmark",
    limit: Optional[int] = -1,
    output_dir: Optional[str] = None,
    is_submission: Optional[bool] = False,
    gpus: Optional[List[int]] = None
):
    gpus = parse_gpu_ids(gpus) if gpus else None
    assert task or hf_dataset_args, "The evaluation data should be specified by either --task or --hf_dataset_args"
    if scenario == "offline":
        try:
            os.makedirs(offline_dir, exist_ok=True)
        except:
            sys.exit(f"Failed to write to offline directory: {offline_dir}.")

    if hf_dataset_args is not None:
        hf_dataset_args = json.loads(hf_dataset_args)
        if task is not None:
            print(f"--task is {task}, but is overwritten by --hf_dataset_args: {hf_dataset_args}")
        task: EfficiencyBenchmarkWrapper = EfficiencyBenchmarkHuggingfaceTask(hf_dataset_args)
    else:
        task: EfficiencyBenchmarkWrapper = TASKS[task]
    metric_task_dict = {}
    prediction_step = PredictStep(
        cmd=cmd,
        task=task,
        scenario=scenario,
        max_batch_size=max_batch_size,
        offline_dir=offline_dir,
        split=split,
        limit=limit,
        is_submission=is_submission,
        gpus=gpus
    )
    if output_dir:
        output_dir = prediction_step.task.base_dir(base_dir=output_dir)
        try:
            os.makedirs(f"{output_dir}/{scenario}/", exist_ok=True)
            print(f"Output to: {output_dir}/{scenario}/")
        except OSError:
            print(f"Failed to create output directory: {output_dir}. Logging to STDOUT.")
            output_dir = None
    predictions, metrics = prediction_step.run()
    if scenario == "accuracy":
        metric_step = CalculateMetricsStep(task=task)
        acc_metrics = metric_step.calculate_metrics(predictions=predictions)
        metric_task_dict[task] = acc_metrics
        if len(acc_metrics.keys()) > 0:
            metrics["accuracy"] = acc_metrics
        output_step = LogOutputStep(task=task, output_file=f"{output_dir}/{scenario}/outputs.json" if output_dir else None)
        output_step.run(predictions=predictions)

    table_step = TabulateMetricsStep()
    table_step_result = table_step.run(metrics=metric_task_dict)

    print("\n".join(table_step_result))
    prediction_step.tabulate_efficiency_metrics(
        metrics,
        output_file=f"{output_dir}/{scenario}/metrics.json" if output_dir else None
    )


@main.command(**_CLICK_COMMAND_DEFAULTS)
@click.argument("cmd", nargs=-1)
@click.option(
    "-t",
    "--task",
    type=str,
    nargs=1,
    help="""Tasks.""",
    default=None
)
@click.option(
    "-h",
    "--hf_dataset_args",
    type=str,
    nargs=1,
    help="""Args for Huggingface load_dataset.""",
    default=None
)
@click.option(
    "-n",
    "--name",
    type=str,
    default=None,
    help="""Name.""",
)
@click.option(
    "--split",
    type=str,
    help="""Split.""",
)
@click.option(
    "-l",
    "--limit",
    type=int,
    default=None,
    help="""Limit.""",
)
@click.option(
    "-b",
    "--max_batch_size",
    type=int,
    default=32,
    help="""Maximum batch size.""",
)
@click.option(
    "--cpus",
    type=float,
    help="""Minimum number of logical CPU cores (e.g. 4.0, 0.5).""",
)
@click.option(
    "--dataset",
    type=str,
    multiple=True,
    help="""An input dataset in the form of 'dataset-name:/mount/location' to attach to your experiment.
    You can specify this option more than once to attach multiple datasets.""",
)
def submit(
    cmd: Tuple[str, ...],
    task: Optional[str] = None,
    hf_dataset_args: Optional[str] = None,
    name: Optional[str] = None,
    split: str = "validation",
    limit: int = None,
    max_batch_size: int = 32,
    cpus: Optional[float] = None,
    dataset: Optional[Tuple[str, ...]] = None,
):
    gantry_run(
        arg=cmd,
        task=task,
        hf_dataset_args=hf_dataset_args,
        name=name,
        split=split,
        limit=limit,
        max_batch_size=max_batch_size,
        cluster=["efficiency-benchmark/elanding-rtx-8000"], # TODO
        beaker_image="haop/efficiency-benchmark",
        workspace="efficiency-benchmark/efficiency-benchmark",
        mount=["/hf_datasets:/hf_datasets"],
        cpus=cpus,
        gpus=2,  # hard code to 2 to make sure only one job runs at a time.
        allow_dirty=True,
        is_submission=True
    )


if __name__ == "__main__":
    main()

import argparse
import numpy as np
import tvm  # noqa: F401
from tvm import relay, transform, autotvm
import tflite
import tensorflow as tf
from tvm.autotvm.tuner import XGBTuner, GATuner, RandomTuner, GridSearchTuner
from tvm.autotvm.graph_tuner import PBQPTuner  # noqa: F401

from pathlib import Path
from typing import Optional

from dl_in_iot_course.misc.pet_dataset import PetDataset
from dl_in_iot_course.l04_tvm.tvm_experiments import TVMModel


class TVMFineTunedModel(TVMModel):
    def __init__(
            self,
            dataset: PetDataset,
            modelpath: Path,
            optlogpath: Path,
            graphoptlogpath: Path,
            originalmodel: Optional[Path] = None,
            logdir: Optional[Path] = None,
            target: str = 'llvm',
            target_host: Optional[str] = None,
            opt_level: int = 3,
            tunertype: str = 'xgb'):
        """
        Initializer for TVMFineTunedModel.

        Parameters
        ----------
        dataset : PetDataset
            A dataset object to test on
        modelpath : Path
            Path to the model to test
        optlogpath : Path
            Path to the log path holding kernel-wise opt log
        graphoptlogpath : Path
            Path to the log path holding graph-wise opt log
        originalmodel : Path
            Path to the model to optimize before testing.
            Optimized model will be saved in modelpath
        logdir : Path
            Path to the training/optimization logs
        target : str
            Target device to run the model on
        target_host : Optional[str]
            Optional directive for the target host
        opt_level : int
            Optimization level for the model
        use_nchw_layout : bool
            Tells is the model in NHWC format should be converted to NCHW
        tunertype : str
            Type of the tuner to use for kernel tuning
        """
        self.tunertype = tunertype
        self.optlogpath = optlogpath
        self.graphoptlogpath = graphoptlogpath
        super().__init__(
            dataset,
            modelpath,
            originalmodel,
            logdir,
            target,
            target_host,
            opt_level,
            True)

    def get_tuner(self, task):
        """
        Creates the tuner object for fine-tuning purposes.

        Parameters
        ----------
        task : tvm.autotvm.task.Task
            Task to create Tuner for

        Returns
        -------
        tvm.autotvm.tuner.Tuner : Tuner for the task
        """
        assert self.tunertype in ['xgb', 'ga', 'random', 'gridsearch']
        if self.tunertype == 'xgb':
            return XGBTuner(task, loss_type='rank')
        elif self.tunertype == 'ga':
            return GATuner(task, pop_size=50)
        elif self.tunertype == 'random':
            return RandomTuner(task)
        elif self.tunertype == 'gridsearch':
            return GridSearchTuner(task)

    def tune_kernels(self, tasks, measure_option):
        """
        Tunes tasks (kernels) present in the model based on measure options.

        Results are saved to self.optlogpath

        Parameters
        ----------
        tasks : List[tvm.autotvm.task.Task]
            List of tasks (kernels) to optimize
        measure_option : dict
            Dictionary generated by tvm.autotvm.measure_option
        """
        # TODO implement
        assert NotImplementedError

    def tune_graph(self, graph):
        """
        Tunes an entire graph based on kernel records.

        Results are saved to self.graphoptlogpath.

        Parameters
        ----------
        graph : tvm.IRModule
            Model module
        """
        # TODO implement
        assert NotImplementedError

    def optimize_model(self, originalmodel: Path):
        with open(originalmodel, 'rb') as f:
            modelfile = f.read()

        tflite_model = tflite.Model.GetRootAsModel(modelfile, 0)  # noqa: F841

        interpreter = tf.lite.Interpreter(model_content=modelfile)
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()[0]
        output_details = interpreter.get_output_details()[0]

        self.input_dtype = input_details['dtype']
        self.input_shape = input_details['shape']
        self.input_name = input_details['name']
        self.output_dtype = output_details['dtype']
        # we do not quantized models in this converter
        assert input_details['dtype'] not in [np.int8, np.uint8]

        mod, params = relay.frontend.from_tflite(
            tflite_model
        )

        transforms = [relay.transform.RemoveUnusedFunctions()]
        transforms.append(
            relay.transform.ConvertLayout({
                "nn.conv2d": ['NCHW', 'default'],
            })
        )

        seq = transform.Sequential(transforms)  # noqa: F841

        with transform.PassContext(opt_level=self.opt_level):
            mod = seq(mod)

        measure_option = autotvm.measure_option(  # noqa: F841
            builder=autotvm.LocalBuilder(),
            runner=autotvm.LocalRunner(
                number=4,
                repeat=10,
                enable_cpu_cache_flush=True
            )
        )

        # TODO finish implementation
        assert NotImplementedError


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--fp32-model-path',
        help='Path to the FP32 TFLite model file',
        type=Path,
        required=True
    )
    parser.add_argument(
        '--dataset-root',
        help='Path to the dataset file',
        type=Path,
        required=True
    )
    parser.add_argument(
        '--download-dataset',
        help='Download the dataset before training',
        action='store_true'
    )
    parser.add_argument(
        '--results-path',
        help='Path to the results',
        type=Path,
        required=True
    )
    parser.add_argument(
        '--test-dataset-fraction',
        help='What fraction of the test dataset should be used for evaluation',
        type=float,
        default=1.0
    )
    parser.add_argument(
        '--target',
        help='The device to run the model on',
        type=str,
        default='llvm -mcpu=core-avx2'
    )
    parser.add_argument(
        '--target-host',
        help='The host CPU type',
        default=None
    )
    parser.add_argument(
        '--tuner-type',
        help='Type of the tuner to use for kernel optimizations',
        default='xgb'
    )

    args = parser.parse_args()

    args.results_path.mkdir(parents=True, exist_ok=True)

    dataset = PetDataset(args.dataset_root, args.download_dataset)

    tester = TVMFineTunedModel(
        dataset,
        args.results_path / f'{args.fp32_model_path.stem}.tvm-tune.so',
        args.results_path / f'{args.fp32_model_path.stem}.tvm-tune.kernellog',
        args.results_path / f'{args.fp32_model_path.stem}.tvm-tune.graphlog',
        args.fp32_model_path,
        args.results_path / 'tvm-tune',
        args.target,
        args.target_host,
        3,
        args.tuner_type
    )
    tester.test_inference(
        args.results_path,
        'tvm-tune',
        args.test_dataset_fraction
    )

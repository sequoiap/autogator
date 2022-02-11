from datetime import datetime
from getpass import getuser
from pathlib import Path
import time
from typing import List

import numpy as np

from autogator.analysis import WavelengthAnalyzer
from autogator.experiment import Experiment
from autogator.hardware import load_default_configuration
from autogator.routines import auto_scan


class WavelengthSweepExperiment(Experiment):
    """
    A wavelength sweep experiment keeps laser power constant, but changes the
    wavelength of the laser. As the laser sweeps, it outputs a trigger signal
    and logs wavelength points. The trigger signal is collected on the
    oscilloscope, which collects data for the entire duration of the sweep,
    and the time-based data is then correlated to the wavelengths as denoted
    by the trigger signal. The data is saved to a text file.

    Parameters
    ----------
    wl_start : float
        The starting wavelength of the sweep.
    wl_stop : float
        The ending wavelength of the sweep.
    duration : float
        The duration of the sweep, in seconds. This will define the sweep rate.
    sample_rate : float
        The sample rate of the oscilloscope.
    trigger_channel : int
        The channel on the oscilloscope that will be used to trigger the data
        collection. This is the laser's output trigger that correlates time
        to logged wavelengths.
    power_dBm : float
        The power of the laser, in dBm.
    buffer : float
        The number of seconds to buffer after collecting data before raising
        a timeout error from the scope.
    active_channels : List[int]
        The oscilloscope channels to collect data on (1-indexed).
    trigger_channel : int
        The channel the laser trigger is conneceted to.
    trigger_level : float
        The trigger voltage to begin data collection at.
    output_dir : str
        The directory to save the data to.
    chip_name : str
    """
    # General configuration
    chip_name: str = "fabrun5"
    output_dir = Path("C:/Users/sequo/Documents/GitHub/autogator/examples/fake")

    # Scope configuration
    duration: float = 5.0
    buffer: float = 5.0
    sample_rate: int = int(np.floor(10e6 / (duration + buffer)))
    sample_rate = 1e5
    active_channels: List[int] = [1, 2]
    trigger_channel: int = 1
    trigger_level: int = 1
    channel_settings = {
        1: {"range": 10, "position": 2},
        2: {"range": 2.5, "position": -1},
        3: {"range": 2.5, "position": -1},
        4: {"range": 2.5, "position": -1},
    }

    # Laser configuration
    wl_start: float = 1500
    wl_stop: float = 1600
    trigger_step: float = 0.01
    power_dBm: float = -4.0

    def setup(self):
        self.operator = input(f"Operator ({getuser()}) [ENTER]: ") 
        if not self.operator: 
            self.operator = getuser()

        self.laser = self.stage.laser.driver
        self.scope = self.stage.scope.driver

        self.laser._pyroClaimOwnership()
        self.laser.on()
        self.laser.open_shutter()

        sweep_rate = (self.wl_stop - self.wl_start) / self.duration
        assert sweep_rate > 1.0
        assert sweep_rate < 100.0
        assert self.wl_start >= 1500  # self.laser.MINIMUM_WAVELENGTH
        assert self.wl_stop <= 1630  # self.laser.MAXIMUM_WAVELENGTH

    def configure_scope_sweep(self):
        acquire_time = self.duration + self.buffer
        numSamples = int((acquire_time) * self.sample_rate)
        print(
            "Set for {:.2E} Samples @ {:.2E} Sa/s.".format(numSamples, self.sample_rate)
        )

        self.scope.acquisition_settings(sample_rate=self.sample_rate, duration=acquire_time)
        for channel in self.active_channels:
            channelMode = "Trigger" if (channel == self.trigger_channel) else "Data"
            print("Adding Channel {} - {}".format(channel, channelMode))
            self.scope.set_channel(channel, **self.channel_settings[channel])
            time.sleep(0.1)

        print("Adding Edge Trigger @ {} Volt(s).".format(self.trigger_level))
        self.scope.edge_trigger(self.trigger_channel, self.trigger_level)

    def configure_scope_measure(self):
        CHANNEL1 = 1
        CHANNEL2 = 2
        RANGE = 2.0
        COUPLING = "DCLimit"
        POSITION = -3.0

        self.scope.set_channel(CHANNEL2, range=RANGE, coupling=COUPLING, position=POSITION)
        self.scope.set_channel(CHANNEL1, range=RANGE, coupling=COUPLING, position=POSITION)
        self.scope.set_auto_measurement(source=F"C{CHANNEL2}W1")
        self.scope.wait_for_device()

        self.scope.edge_trigger(1, 0.0)
        self.scope.set_timescale(10e-10) 
        self.scope.acquire(run="continuous")

        time.sleep(5)
        print("Test read:", self.stage.scope.measure())

    def configure_laser_sweep(self):
        self.laser.power_dBm(self.power_dBm)
        self.laser.sweep_set_mode(
            continuous=True, twoway=True, trigger=False, const_freq_step=False
        )

        print("Enabling self.laser's trigger output.")
        self.laser.trigger_enable_output()
        triggerMode = self.laser.trigger_set_mode("Step")
        triggerStep = self.laser.trigger_step(self.trigger_step)
        print("Setting trigger to: {} and step to {}".format(triggerMode, triggerStep))

    def configure_laser_measure(self):
        self.laser.wavelength(1550.0)

    def run(self):
        print(self.circuit)

        self.configure_scope_measure()
        self.configure_laser_measure()

        auto_scan(stage=self.stage, daq=self.stage.scope, settle=0.0, plot=True)

        self.configure_scope_sweep()
        self.configure_laser_sweep()

        print("Starting Acquisition")
        self.scope.acquire(timeout=self.duration * 2)
        print("Sweeping laser")
        self.laser.sweep_wavelength(self.wl_start, self.wl_stop, self.duration)
        print("Waiting for acquisition to complete...")
        print(self.scope.timeout)
        self.scope.wait_for_device()

        print("Getting raw data...")
        raw = {}
        for channel in self.active_channels:
            print(channel)
            raw[channel] = self.scope.get_data(channel)
        wavelengthLog = self.laser.wavelength_logging()

        print("Processing Data")
        analysis = WavelengthAnalyzer(
            sample_rate=self.sample_rate,
            wavelength_log=wavelengthLog,
            trigger_data=raw[self.trigger_channel],
        )

        sorted_data = {
            channel: analysis.process_data(raw[channel])
            for channel in self.active_channels
        }

        today = datetime.now()
        date_prefix = f"{today.year}_{today.month}_{today.day}_{today.hour}_{today.minute}_"
        filename = self.output_dir / f"{date_prefix}_{self.chip_name}_locx_{self.circuit.loc.x}_locy_{self.circuit.loc.y}".replace(".", "p")
        filename = filename.with_suffix(".wlsweep")
        
        FILE_HEADER = f"""# Test performed at {today.strftime("%Y-%m-%d %H:%M:%S")}
# Operator: {self.operator}
# Chip: {self.chip_name}
# Circuit: {self.circuit.loc.x}, {self.circuit.loc.y}
# Laser: {self.laser.wavelength()}
# Laser power: {self.power_dBm} dBm
# Wavelength start: {self.wl_start} nm
# Wavelength stop: {self.wl_stop} nm
#
# Wavelength\tCh1\tCh2\tCh3\tCh4
"""

        print("Saving raw data.")
        with filename.open("w") as out:
            out.write(FILE_HEADER)
            data_lists = [sorted_data[self.trigger_channel]["wavelengths"]]
            for channel in raw:
                data_lists.append(sorted_data[channel]["data"])
            data_zip = zip(*data_lists)
            for data_list in data_zip:
                for data in data_list:
                    out.write(str(data) + "\t")
                out.write("\n")

    def teardown(self):
        pass


if __name__ == "__main__":
    from autogator.circuit import CircuitMap
    from autogator.experiment import ExperimentRunner

    cmap = CircuitMap.loadtxt("data/circuitmap.txt")

    mzi2 = cmap.filterby(name="MZI2", grouping="1")
    filt2 = CircuitMap([m for m in mzi2 if m.loc.x == -3030.0])
    stage = load_default_configuration().get_stage()
    try:
        runner = ExperimentRunner(filt2, WavelengthSweepExperiment, stage=stage)
        runner.run()
    except Exception as e:
        print(stage.scope.measure())
        raise e

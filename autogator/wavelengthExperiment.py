from typing import Dict

from autogator.Experiment import Experiment
from pyrolab.analysis import WavelengthAnalyzer


class WavelengthSweepExperiment(Experiment):
    def __init__(
        self,
        wl_start=1500: float,
        wl_stop=1600: float,
        duration=15.0: float,
        sample_rate=10e09: float,
        trigger_step=0.01: float,
        power_dBm=12.0: float,
        buffer=2.0: float,
        active_channels=[1, 2, 3, 4]: List[int],
        trigger_channel=1: int,
        trigger_level=1: int,
        output_dir="C:\\Users\\mcgeo\\source\\repos\\autogator\\autogator\\data\\": str,
        take_screenshot=True: bool,
        save_raw_data=False: bool,
    ):
        super().__init__()
        self.channel_settings = {}
        self.wl_start = wl_start
        self.wl_stop = wl_stop
        self.duration = duration
        self.sample_rate = sample_rate
        self.trigger_step = trigger_step
        self.power_dBm = power_dBm
        self.buffer = buffer
        self.active_channels = active_channels
        self.trigger_channel = trigger_channel
        self.trigger_level = trigger_level
        self.take_screenshot = take_screenshot
        self.save_raw_data = save_raw_data
        self.output_dir = output_dir
        today = datetime.now()
        datePrefix = "{}_{}_{}_{}_{}_".format(today.year, today.month, today.day, today.hour, today.minute)
        self.filename = datePrefix + ".Wavelength_Sweep"

    def configure_channel(self, channel: int, params: Dict[str, Any]):
        self.channel_setting[channel] = params

    def run(self):
        laser = self.dataCache.get_laser()
        scope = self.dataCache.get_scope()

        sweep_rate = (lambda_stop - lambda_start) / duration
        assert sweep_rate > 1.0 
        assert sweep_rate < 100.0
        assert wl_start >= laser.MINIMUM_WAVELENGTH
        assert wl_stop <= laser.MAXIMUM_WAVELENGTH

        laser.on()
        laser.power_dBm(self.power_dBm)
        laser.open_shutter()
        laser.sweep_set_mode(continuous=True, twoway=True, trigger=False, const_freq_step=False)
        print("Enabling laser's trigger output.")
        laser.trigger_enable_output()
        triggerMode = laser.trigger_set_mode("Step")
        triggerStep = laser.trigger_set_step(self.trigger_step)
        print("Setting trigger to: {} and step to {}".format(triggerMode, triggerStep))

        acquire_time = self.duration + self.buffer
        numSamples = int((acquire_time) * self.sample_rate)
        print("Set for {:.2E} Samples @ {:.2E} Sa/s.".format(numSamples, self.sample_rate))

        scope.acquisition_settings(self.sample_rate, acquire_time)
        for channel in self.active_channels:
            channelMode = "Trigger" if (channel == self.trigger_channel) else "Data"
            print("Adding Channel {} - {}".format(channel, channelMode))
            scope.set_channel(channel, **channel_setting[channel])
        print("Adding Edge Trigger @ {} Volt(s).".format(self.trigger_level))
        scope.edge_trigger(self.trigger_channel, self.trigger_level)

        print('Starting Acquisition')
        scope.start_acquisition(timeout = self.duration*3)

        print('Sweeping Laser')
        laser.sweep_wavelength(self.wl_start, self.wl_stop, self.duration)

        print('Waiting for acquisition to complete.')
        scope.wait_for_device()

        if self.take_screenshot:
            scope.screenshot(self.output_dir + "screenshot.png")

        rawData = [None] #Ugly hack to make the numbers line up nicely.
        rawData[1:] = [scope.get_data_ascii(channel) for channel in self.active_channels]
        wavelengthLog = laser.wavelength_logging()
        wavelengthLogSize = laser.wavelength_logging_number()

        if self.save_raw_data:
            print("Saving raw data.")
            for channel in self.active_channels:
                with open(output_dir + "CHAN{}_Raw.txt".format(channel), "w") as out:
                    out.write(str(rawData[channel]))
            with open(output_dir + "Wavelength_Log.txt", "w") as out:
                out.write(str(wavelengthLog))

        print("Processing Data")
        analysis = WavelengthAnalyzer(
            sample_rate = self.sample_rate,
            wavelength_log = wavelengthLog,
            trigger_data = rawData[self.trigger_channel]
        )

        print('=' * 30)
        print("Expected number of wavelength points: " + str(int(wavelengthLogSize)))
        print("Measured number of wavelength points: " + str(analysis.num_peaks()))
        print('=' * 30)

        data = [None] #Really ugly hack to make index numbers line up.
        data[1:] = [
            analysis.process_data(rawData[channel]) for channel in self.active_channels
        ]

        print("Raw Datasets: {}".format(len(rawData)))
        print("Datasets Returned: {}".format((len(data))))

        for channel in self.active_channels:
            if (channel != self.trigger_channel):
                print("Displaying data for channel " + str(channel))
                VisualizeData(output_dir + self.filename, channel, **(data[channel]))

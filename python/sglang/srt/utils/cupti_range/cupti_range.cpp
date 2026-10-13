#include <torch/extension.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include <cupti_range_profiler.h>
#include <cupti_profiler_target.h>
#include <cupti_profiler_host.h>
#include <cupti_target.h>
#include <nvperf_host.h>
#include <nvperf_cuda_host.h>
#include <nvperf_target.h>

#include <atomic>
#include <cstdio>
#include <functional>
#include <thread>
#include <unistd.h>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include "Metric.h"

namespace {
constexpr size_t kMaxRanges = 8192;
const std::vector<std::string> kMetricNames = {
    "gpu__time_duration.avg",
    "sm__cycles_active.avg.pct_of_peak_sustained_elapsed",
    "sm__cycles_active.avg.pct_of_peak_sustained_active",
    "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active",
    "dram__bytes_read.sum",
    "dram__bytes_write.sum",
    "gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed",
};

std::string result_string(CUptiResult result) {
    const char* value = "unknown CUPTI error";
    cuptiGetResultString(result, &value);
    return value ? value : "unknown CUPTI error";
}
void check(CUptiResult result, const char* operation) {
    if (result != CUPTI_SUCCESS) {
        throw std::runtime_error(std::string(operation) + ": " + result_string(result));
    }
}

class RangeSession {
public:
    static RangeSession& instance() {
        static RangeSession session;
        return session;
    }

    void initialize() {
        std::lock_guard<std::mutex> guard(mutex_);
        if (initialized_) return;
        if (const auto stale = cudaGetLastError(); stale != cudaSuccess) {
            throw std::runtime_error(std::string("stale CUDA runtime error before CUPTI init: ") + cudaGetErrorString(stale));
        }
        const cudaError_t bootstrap = cudaFree(0);
        if (bootstrap != cudaSuccess) {
            throw std::runtime_error(std::string("cudaFree(0) context bootstrap: ") +
                                     cudaGetErrorString(bootstrap));
        }
        // Called on the scheduler's model-execution thread after CUDA Graph
        // capture. This resolves PyTorch's existing primary context; no context
        // is created or switched here.
        CUcontext context = nullptr;
        check_driver(cuCtxGetCurrent(&context), "cuCtxGetCurrent");
        if (!context) throw std::runtime_error("no current scheduler CUDA context");
        CUdevice device = 0;
        check_driver(cuCtxGetDevice(&device), "cuCtxGetDevice");
        cudaStreamCaptureStatus capture_status{};
        const cudaError_t capture_status_result = cudaStreamIsCapturing(nullptr, &capture_status);
        if (capture_status_result != cudaSuccess) {
            throw std::runtime_error(std::string("cudaStreamIsCapturing: ") + cudaGetErrorString(capture_status_result));
        }
        if (capture_status != cudaStreamCaptureStatusNone) {
            throw std::runtime_error("CUPTI initialization attempted during stream capture");
        }
        capture_status_ = static_cast<int>(capture_status);
        int runtime_device = -1;
        const cudaError_t get_device_status = cudaGetDevice(&runtime_device);
        if (get_device_status != cudaSuccess) {
            throw std::runtime_error(std::string("cudaGetDevice: ") + cudaGetErrorString(get_device_status));
        }
        int context_device = -1;
        check_driver(cuCtxGetDevice(&device), "cuCtxGetDevice");
        context_device = static_cast<int>(device);
        std::fprintf(stderr,
                     "T002_CUPTI_INIT pid=%d tid=%zu ctx=%p driver_device=%d runtime_device=%d cuda_version=",
                     static_cast<int>(getpid()), std::hash<std::thread::id>{}(std::this_thread::get_id()),
                     static_cast<void*>(context), context_device, runtime_device);
        int runtime_version = 0;
        cudaRuntimeGetVersion(&runtime_version);
        std::fprintf(stderr, "%d\\n", runtime_version);
        std::fflush(stderr);

        CUpti_Profiler_Initialize_Params init{CUpti_Profiler_Initialize_Params_STRUCT_SIZE};
        check(cuptiProfilerInitialize(&init), "cuptiProfilerInitialize");
        CUpti_Profiler_DeviceSupported_Params supported{
            CUpti_Profiler_DeviceSupported_Params_STRUCT_SIZE};
        supported.cuDevice = static_cast<size_t>(device);
        supported.api = CUPTI_PROFILER_RANGE_PROFILING;
        check(cuptiProfilerDeviceSupported(&supported), "cuptiProfilerDeviceSupported");
        if (supported.isSupported != CUPTI_PROFILER_CONFIGURATION_SUPPORTED)
            throw std::runtime_error("CUPTI range profiling unsupported on current GPU");

        CUpti_Device_GetChipName_Params chip{CUpti_Device_GetChipName_Params_STRUCT_SIZE};
        chip.deviceIndex = static_cast<size_t>(device);
        check(cuptiDeviceGetChipName(&chip), "cuptiDeviceGetChipName");
        CUpti_Profiler_GetCounterAvailability_Params availability{
            CUpti_Profiler_GetCounterAvailability_Params_STRUCT_SIZE};
        availability.ctx = context;
        check(cuptiProfilerGetCounterAvailability(&availability), "counter availability size");
        availability_.resize(availability.counterAvailabilityImageSize);
        availability.pCounterAvailabilityImage = availability_.data();
        check(cuptiProfilerGetCounterAvailability(&availability), "counter availability");

        CUpti_Profiler_Host_Initialize_Params host_init{
            CUpti_Profiler_Host_Initialize_Params_STRUCT_SIZE};
        host_init.profilerType = CUPTI_PROFILER_TYPE_RANGE_PROFILER;
        host_init.pChipName = chip.pChipName;
        host_init.pCounterAvailabilityImage = availability_.data();
        check(cuptiProfilerHostInitialize(&host_init), "cuptiProfilerHostInitialize");
        host_ = host_init.pHostObject;
        metric_ptrs_.reserve(kMetricNames.size());
        for (const auto& name : kMetricNames) metric_ptrs_.push_back(name.c_str());
        CUpti_Profiler_Host_ConfigAddMetrics_Params add_metrics{
            CUpti_Profiler_Host_ConfigAddMetrics_Params_STRUCT_SIZE};
        add_metrics.pHostObject = host_;
        add_metrics.ppMetricNames = metric_ptrs_.data();
        add_metrics.numMetrics = metric_ptrs_.size();
        check(cuptiProfilerHostConfigAddMetrics(&add_metrics), "cuptiProfilerHostConfigAddMetrics");
        if (!NV::Metric::Config::GetConfigImage(
                chip.pChipName, kMetricNames, config_, availability_.data()))
            throw std::runtime_error("NVPW config image generation failed");

        CUpti_Profiler_Host_GetNumOfPasses_Params passes{
            CUpti_Profiler_Host_GetNumOfPasses_Params_STRUCT_SIZE};
        passes.pConfigImage = config_.data();
        passes.configImageSize = config_.size();
        check(cuptiProfilerHostGetNumOfPasses(&passes), "cuptiProfilerHostGetNumOfPasses");
        if (passes.numOfPasses != 1)
            throw std::runtime_error("core CUPTI metric set is not single pass");
        pass_count_ = passes.numOfPasses;

        CUpti_RangeProfiler_Enable_Params enable{CUpti_RangeProfiler_Enable_Params_STRUCT_SIZE};
        enable.ctx = context;
        if (cudaStreamCaptureStatus capture_status{}; cudaStreamIsCapturing(nullptr, &capture_status) == cudaSuccess && capture_status != cudaStreamCaptureStatusNone) {
            throw std::runtime_error("cannot enable CUPTI during CUDA stream capture");
        }
        const CUptiResult enable_status = cuptiRangeProfilerEnable(&enable);
        if (enable_status != CUPTI_SUCCESS) {
            std::fprintf(stderr, "T002_CUPTI_ENABLE_DIAG result=%d object=%p ctx=%p\\n",
                         static_cast<int>(enable_status),
                         static_cast<void*>(enable.pRangeProfilerObject),
                         static_cast<void*>(context));
            std::fflush(stderr);
            check(enable_status, "cuptiRangeProfilerEnable");
        }
        object_ = enable.pRangeProfilerObject;
        std::fprintf(stderr, "T002_CUPTI_ENABLED object=%p ctx=%p pid=%d tid=%zu\\n",
                     static_cast<void*>(object_), static_cast<void*>(context),
                     static_cast<int>(getpid()), std::hash<std::thread::id>{}(std::this_thread::get_id()));
        std::fflush(stderr);
        CUpti_RangeProfiler_GetCounterDataSize_Params data_size{
            CUpti_RangeProfiler_GetCounterDataSize_Params_STRUCT_SIZE};
        data_size.pRangeProfilerObject = object_;
        data_size.pMetricNames = metric_ptrs_.data();
        data_size.numMetrics = metric_ptrs_.size();
        data_size.maxNumOfRanges = kMaxRanges;
        data_size.maxNumRangeTreeNodes = kMaxRanges;
        check(cuptiRangeProfilerGetCounterDataSize(&data_size), "counter data size");
        counter_data_.resize(data_size.counterDataSize);
        CUpti_RangeProfiler_CounterDataImage_Initialize_Params data_init{
            CUpti_RangeProfiler_CounterDataImage_Initialize_Params_STRUCT_SIZE};
        data_init.pRangeProfilerObject = object_;
        data_init.pCounterData = counter_data_.data();
        data_init.counterDataSize = counter_data_.size();
        check(cuptiRangeProfilerCounterDataImageInitialize(&data_init), "counter data initialize");
        CUpti_RangeProfiler_SetConfig_Params set_config{
            CUpti_RangeProfiler_SetConfig_Params_STRUCT_SIZE};
        set_config.pRangeProfilerObject = object_;
        set_config.pConfig = config_.data();
        set_config.configSize = config_.size();
        set_config.pCounterDataImage = counter_data_.data();
        set_config.counterDataImageSize = counter_data_.size();
        set_config.range = CUPTI_UserRange;
        set_config.replayMode = CUPTI_UserReplay;
        set_config.maxRangesPerPass = kMaxRanges;
        set_config.numNestingLevels = 1;
        set_config.minNestingLevel = 1;
        set_config.passIndex = 0;
        set_config.targetNestingLevel = 1;
        const CUptiResult config_status = cuptiRangeProfilerSetConfig(&set_config);
        if (config_status != CUPTI_SUCCESS) {
            std::fprintf(stderr, "T002_CUPTI_SETCONFIG_DIAG result=%d object=%p ctx=%p image=%p size=%zu data=%p data_size=%zu range=%d replay=%d pass=%zu\\n",
                         static_cast<int>(config_status), static_cast<void*>(object_),
                         static_cast<void*>(context), static_cast<void*>(config_.data()),
                         config_.size(), static_cast<void*>(counter_data_.data()),
                         counter_data_.size(), static_cast<int>(set_config.range),
                         static_cast<int>(set_config.replayMode), set_config.passIndex);
            std::fflush(stderr);
            check(config_status, "cuptiRangeProfilerSetConfig");
        }
        std::fprintf(stderr, "T002_CUPTI_SETCONFIG_OK object=%p ctx=%p image=%p size=%zu data=%p data_size=%zu range=%d replay=%d pass=%zu thread=%zu\\n",
                     static_cast<void*>(object_), static_cast<void*>(context),
                     static_cast<void*>(config_.data()), config_.size(),
                     static_cast<void*>(counter_data_.data()), counter_data_.size(),
                     static_cast<int>(set_config.range), static_cast<int>(set_config.replayMode),
                     set_config.passIndex, std::hash<std::thread::id>{}(std::this_thread::get_id()));
        std::fflush(stderr);
        context_ = context;
        initialized_ = true;
    }

    void begin(const std::string& range_id, int64_t iteration, const std::string& stage,
               int64_t batch, int64_t tokens, const std::string& graph) {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!enabled_.load(std::memory_order_relaxed)) return;
        initialize_unlocked();
        assert_context();
        if (active_) throw std::runtime_error("nested CUPTI user ranges are not supported");
        if (started_count_ >= kMaxRanges) throw std::runtime_error("CUPTI range limit reached");
        labels_.push_back("range=" + range_id + ";iter=" + std::to_string(iteration) +
                          ";stage=" + stage + ";batch=" + std::to_string(batch) +
                          ";tokens=" + std::to_string(tokens) + ";graph=" + graph);
        if (!profiler_started_) throw std::runtime_error("CUPTI window not started");
        push_.pRangeProfilerObject = object_;
        push_.pRangeName = labels_.back().c_str();
        check(cuptiRangeProfilerPushRange(&push_), "cuptiRangeProfilerPushRange");
        active_ = true;
    }

    void end() {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!active_) return;
        pop_.pRangeProfilerObject = object_;
        check(cuptiRangeProfilerPopRange(&pop_), "cuptiRangeProfilerPopRange");
        stop_.pRangeProfilerObject = object_;
        check(cuptiRangeProfilerStop(&stop_), "cuptiRangeProfilerStop");
        active_ = false;
        profiler_started_ = false;
        if (!stop_.isAllPassSubmitted)
            throw std::runtime_error("CUPTI one-pass range did not submit all passes");
        ++started_count_;
    }

    void set_enabled(bool value) {
        enabled_.store(value, std::memory_order_relaxed);
        if (value) initialize();
    }

    void disable() {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!object_) return;
        disable_.pRangeProfilerObject = object_;
        check(cuptiRangeProfilerDisable(&disable_), "cuptiRangeProfilerDisable");
        object_ = nullptr;
        host_ = nullptr;
        initialized_ = false;
        profiler_started_ = false;
        std::fprintf(stderr, "T002_CUPTI_DISABLED pid=%d tid=%zu\\n", static_cast<int>(getpid()),
                     std::hash<std::thread::id>{}(std::this_thread::get_id()));
        std::fflush(stderr);
    }

    void arm_window() {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!initialized_) throw std::runtime_error("CUPTI profiler not initialized");
        assert_context();
        if (profiler_started_) throw std::runtime_error("CUPTI profiler already started");
        CUpti_RangeProfiler_Enable_Params enable{CUpti_RangeProfiler_Enable_Params_STRUCT_SIZE};
        enable.ctx = context_;
        check(cuptiRangeProfilerEnable(&enable), "enable fresh range profiler object");
        object_ = enable.pRangeProfilerObject;
        CUpti_RangeProfiler_GetCounterDataSize_Params size{
            CUpti_RangeProfiler_GetCounterDataSize_Params_STRUCT_SIZE};
        size.pRangeProfilerObject = object_;
        size.pMetricNames = metric_ptrs_.data();
        size.numMetrics = metric_ptrs_.size();
        size.maxNumOfRanges = kMaxRanges;
        size.maxNumRangeTreeNodes = kMaxRanges;
        check(cuptiRangeProfilerGetCounterDataSize(&size), "fresh counter data size");
        counter_data_.resize(size.counterDataSize);
        CUpti_RangeProfiler_CounterDataImage_Initialize_Params image{
            CUpti_RangeProfiler_CounterDataImage_Initialize_Params_STRUCT_SIZE};
        image.pRangeProfilerObject = object_;
        image.pCounterData = counter_data_.data();
        image.counterDataSize = counter_data_.size();
        check(cuptiRangeProfilerCounterDataImageInitialize(&image), "fresh counter data image");
        CUpti_RangeProfiler_SetConfig_Params config{
            CUpti_RangeProfiler_SetConfig_Params_STRUCT_SIZE};
        config.pRangeProfilerObject = object_;
        config.pConfig = config_.data();
        config.configSize = config_.size();
        config.pCounterDataImage = counter_data_.data();
        config.counterDataImageSize = counter_data_.size();
        config.range = CUPTI_UserRange;
        config.replayMode = CUPTI_UserReplay;
        config.maxRangesPerPass = kMaxRanges;
        config.numNestingLevels = 1;
        config.minNestingLevel = 1;
        config.passIndex = 0;
        config.targetNestingLevel = 1;
        check(cuptiRangeProfilerSetConfig(&config), "set fresh range config");
        start_.pRangeProfilerObject = object_;
        const CUptiResult status = cuptiRangeProfilerStart(&start_);
        std::fprintf(stderr, "T002_CUPTI_WINDOW_START result=%d object=%p ctx=%p pid=%d tid=%zu\\n",
                     static_cast<int>(status), static_cast<void*>(object_),
                     static_cast<void*>(context_), static_cast<int>(getpid()),
                     std::hash<std::thread::id>{}(std::this_thread::get_id()));
        std::fflush(stderr);
        check(status, "cuptiRangeProfilerStart(window)");
        profiler_started_ = true;
    }

    pybind11::dict finalize() {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!initialized_) throw std::runtime_error("CUPTI range session was never initialized");
        if (active_) throw std::runtime_error("cannot decode while range is active");
        assert_context();
        // The only device-wide sync is at the bounded measurement window end.
        check(cudaDeviceSynchronize() == cudaSuccess ? CUPTI_SUCCESS : CUPTI_ERROR_UNKNOWN,
              "window-end cudaDeviceSynchronize");
        decode_.pRangeProfilerObject = object_;
        check(cuptiRangeProfilerDecodeData(&decode_), "cuptiRangeProfilerDecodeData");
        CUpti_RangeProfiler_GetCounterDataInfo_Params info{
            CUpti_RangeProfiler_GetCounterDataInfo_Params_STRUCT_SIZE};
        info.pCounterDataImage = counter_data_.data();
        info.counterDataImageSize = counter_data_.size();
        check(cuptiRangeProfilerGetCounterDataInfo(&info), "cuptiRangeProfilerGetCounterDataInfo");
        pybind11::list ranges;
        for (size_t index = 0; index < info.numTotalRanges; ++index) {
            CUpti_RangeProfiler_CounterData_GetRangeInfo_Params range_info{
                CUpti_RangeProfiler_CounterData_GetRangeInfo_Params_STRUCT_SIZE};
            range_info.pCounterDataImage = counter_data_.data();
            range_info.counterDataImageSize = counter_data_.size();
            range_info.rangeIndex = index;
            range_info.rangeDelimiter = "/";
            check(cuptiRangeProfilerCounterDataGetRangeInfo(&range_info), "range name");
            std::vector<double> values(kMetricNames.size());
            CUpti_Profiler_Host_EvaluateToGpuValues_Params evaluate{
                CUpti_Profiler_Host_EvaluateToGpuValues_Params_STRUCT_SIZE};
            evaluate.pHostObject = host_;
            evaluate.pCounterDataImage = counter_data_.data();
            evaluate.counterDataImageSize = counter_data_.size();
            evaluate.ppMetricNames = metric_ptrs_.data();
            evaluate.numMetrics = metric_ptrs_.size();
            evaluate.rangeIndex = index;
            evaluate.pMetricValues = values.data();
            check(cuptiProfilerHostEvaluateToGpuValues(&evaluate), "evaluate range metrics");
            pybind11::dict row;
            row["name"] = range_info.rangeName;
            for (size_t metric = 0; metric < kMetricNames.size(); ++metric)
                row[pybind11::str(kMetricNames[metric])] = values[metric];
            ranges.append(row);
        }
        pybind11::dict result;
        result["ranges"] = ranges;
        result["range_count"] = info.numTotalRanges;
        result["expected_range_count"] = started_count_;
        result["dropped"] = decode_.numOfRangeDropped;
        result["passes"] = pass_count_;
        return result;
    }

private:
    void initialize_unlocked() {
        if (!initialized_) throw std::runtime_error("enable CUPTI on scheduler CUDA thread first");
    }
    void assert_context() const {
        CUcontext current = nullptr;
        check_driver(cuCtxGetCurrent(&current), "cuCtxGetCurrent");
        if (current != context_) throw std::runtime_error("CUPTI CUDA context changed");
    }
    static void check_driver(CUresult result, const char* operation) {
        if (result != CUDA_SUCCESS) {
            const char* message = "unknown CUDA driver error";
            cuGetErrorString(result, &message);
            throw std::runtime_error(std::string(operation) + ": " + message);
        }
    }
    std::mutex mutex_;
    std::atomic<bool> enabled_{false};
    bool initialized_ = false, active_ = false, profiler_started_ = false;
    CUcontext context_ = nullptr;
    int capture_status_ = -1;
    CUpti_RangeProfiler_Object* object_ = nullptr;
    CUpti_Profiler_Host_Object* host_ = nullptr;
    size_t pass_count_ = 0, started_count_ = 0;
    std::vector<uint8_t> availability_, config_, counter_data_;
    std::vector<const char*> metric_ptrs_;
    std::vector<std::string> labels_;
    CUpti_RangeProfiler_Start_Params start_{CUpti_RangeProfiler_Start_Params_STRUCT_SIZE};
    CUpti_RangeProfiler_PushRange_Params push_{CUpti_RangeProfiler_PushRange_Params_STRUCT_SIZE};
    CUpti_RangeProfiler_PopRange_Params pop_{CUpti_RangeProfiler_PopRange_Params_STRUCT_SIZE};
    CUpti_RangeProfiler_Stop_Params stop_{CUpti_RangeProfiler_Stop_Params_STRUCT_SIZE};
    CUpti_RangeProfiler_DecodeData_Params decode_{CUpti_RangeProfiler_DecodeData_Params_STRUCT_SIZE};
    CUpti_RangeProfiler_Disable_Params disable_{CUpti_RangeProfiler_Disable_Params_STRUCT_SIZE};
};
}  // namespace

void enable(bool value) { RangeSession::instance().set_enabled(value); }
void arm_window() { RangeSession::instance().arm_window(); }
void begin_range(const std::string& range, int64_t iteration, const std::string& stage,
                 int64_t batch, int64_t tokens, const std::string& graph) {
    RangeSession::instance().begin(range, iteration, stage, batch, tokens, graph);
}
void end_range() { RangeSession::instance().end(); }
void disable() { RangeSession::instance().disable(); }
pybind11::dict finalize() { return RangeSession::instance().finalize(); }

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
    module.def("enable", &enable);
    module.def("arm_window", &arm_window);
    module.def("begin", &begin_range);
    module.def("end", &end_range);
    module.def("disable", &disable);
    module.def("finalize", &finalize);
}

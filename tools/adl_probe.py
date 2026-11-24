import ctypes

class ADLSingleSensorData(ctypes.Structure):
    _fields_ = [("supported", ctypes.c_int), ("value", ctypes.c_int)]

class ADLPMLogDataOutput(ctypes.Structure):
    _fields_ = [("size", ctypes.c_int), ("sensors", ADLSingleSensorData * 256)]

class ADLAdapterInfo(ctypes.Structure):
    _fields_ = [("iSize", ctypes.c_int), ("iAdapterIndex", ctypes.c_int),
                ("strUDID", ctypes.c_char * 256), ("iBusNumber", ctypes.c_int),
                ("iDeviceNumber", ctypes.c_int), ("iFunctionNumber", ctypes.c_int),
                ("iVendorID", ctypes.c_int), ("strAdapterName", ctypes.c_char * 256),
                ("strDisplayName", ctypes.c_char * 256), ("iPresent", ctypes.c_int),
                ("iExist", ctypes.c_int), ("strDriverPath", ctypes.c_char * 256),
                ("strDriverPathExt", ctypes.c_char * 256), ("strPNPString", ctypes.c_char * 256),
                ("iOSDisplayIndex", ctypes.c_int)]

ALLOC_CB = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
adl = ctypes.CDLL(r"C:\Windows\System32\atiadlxx.dll")
ctx = ctypes.c_void_p()
adl.ADL2_Main_Control_Create.argtypes = [ALLOC_CB, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
adl.ADL2_Main_Control_Create(ALLOC_CB(lambda s: ctypes.cast(ctypes.create_string_buffer(s), ctypes.c_void_p)), 1, ctypes.byref(ctx))

fn = adl.ADL2_New_QueryPMLogData_Get
fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ADLPMLogDataOutput)]

for size_val in (2048, 2052):
    data = ADLPMLogDataOutput()
    ctypes.memset(ctypes.byref(data), 0xFF, ctypes.sizeof(data))
    data.size = size_val
    rc = fn(ctx, 0, ctypes.byref(data))
    print(f"### size={size_val} rc={rc} returned_size={data.size}")
    for i in range(0, 90):
        s = data.sensors[i]
        if s.supported not in (0, 0xFFFFFFFF):
            print(f"  [{i:3d}] supported={s.supported} (0x{s.supported:X}) value={s.value}")

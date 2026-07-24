PROGRAM PLC_PRG

(* MainTask 入口：HMI 交互 -> 设备逻辑；PRG_Axis_Control 在 ETHERCAT 任务独立运行 *)
PRG_TcpHmi();
PRG_Logic();

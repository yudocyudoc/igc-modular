model DStockFlow_5bc57655500f
  // Generic balance grammar; no molecular wrapper; no fitted parameter.
  parameter Real pulseRate = 1.7;
  parameter Real pulseDuration = 2;
  parameter Real capacity = 2;
  parameter Real responseTime = 1;
  parameter Real lossTime = 3;
  Real inputRate;
  Real s1(start=0, fixed=true);
  Real f1;
  Real lossRate;
  Real delivered(start=0, fixed=true);
  Real lost(start=0, fixed=true);
equation
  inputRate = if time < pulseDuration then pulseRate else 0;
  f1 = min(capacity, max(0, s1/responseTime));
  lossRate = max(0, s1/lossTime);
  der(s1) = inputRate - f1 - lossRate;
  der(delivered) = f1;
  der(lost) = lossRate;
end DStockFlow_5bc57655500f;

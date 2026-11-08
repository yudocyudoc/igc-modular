model DStockFlow_1b03f4d80336
  // Generic balance grammar; no molecular wrapper; no fitted parameter.
  parameter Real pulseRate = 1.7;
  parameter Real pulseDuration = 2;
  parameter Real capacity = 2;
  parameter Real responseTime = 1;
  parameter Real lossTime = 3;
  Real inputRate;
  Real s1(start=0, fixed=true);
  Real s2(start=0, fixed=true);
  Real f1;
  Real f2;
  Real lossRate;
  Real delivered(start=0, fixed=true);
  Real lost(start=0, fixed=true);
equation
  inputRate = if time < pulseDuration then pulseRate else 0;
  f1 = min(capacity, max(0, s1/responseTime));
  f2 = min(capacity, max(0, s2/responseTime));
  lossRate = 0;
  der(s1) = inputRate - f1 - lossRate;
  der(s2) = f1 - f2;
  der(delivered) = f2;
  der(lost) = lossRate;
end DStockFlow_1b03f4d80336;

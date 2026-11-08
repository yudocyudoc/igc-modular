within;
package IGCMolecules
  "IGC molecular subassemblies: all differential/rate behavior is from existing libraries"
  model AcceptedSource
    "Trusted incoming accepted work, not inferred arrivals"
    Modelica.Blocks.Interfaces.RealInput externalRate;
    Modelica.Blocks.Interfaces.RealOutput outflow;
    SystemDynamics.Rates.Rate_1 incoming;
  equation
    connect(externalRate,incoming.u);
    connect(incoming.y,outflow);
  end AcceptedSource;

  model BoundedQueue
    "A functional molecule: stock + bounded release + proportional response"
    parameter Real maxThroughput(min=0);
    parameter Real responseTime(min=1e-9);
    Modelica.Blocks.Interfaces.RealInput arrival;
    Modelica.Blocks.Interfaces.RealOutput completed;
    Modelica.Blocks.Interfaces.RealOutput waiting;
    SystemDynamics.Levels.Level stock(x0=0);
    SystemDynamics.Rates.Rate_1 inflow;
    SystemDynamics.Rates.RRate release(minFlow=0,maxFlow=maxThroughput);
    Modelica.Blocks.Math.Gain response(k=1/responseTime);
  equation
    connect(arrival,inflow.u);
    connect(inflow.y,stock.u1);
    connect(release.y1,stock.u2);
    response.u = stock.level;
    connect(response.y,release.u);
    connect(release.y,completed);
    waiting = stock.level;
  end BoundedQueue;

  model DeliveryCounter
    "Terminal stock for recorded deliveries; no scheduling policy"
    Modelica.Blocks.Interfaces.RealInput arrival;
    Modelica.Blocks.Interfaces.RealOutput total;
    SystemDynamics.Rates.Rate_1 incoming;
    SystemDynamics.Levels.Level1a deliveries(x0=0);
  equation
    connect(arrival,incoming.u);
    connect(incoming.y,deliveries.u1);
    total = deliveries.level;
  end DeliveryCounter;
  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));
end IGCMolecules;

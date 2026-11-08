within;
package IGCInformationMolecules
  model FirstOrderReportFilter
    "Information-only low-pass display of physical receipt-rate; not a physical shipment queue"
    parameter Real reportResponseTime(min=1e-9)=0.8;
    Modelica.Blocks.Interfaces.RealInput physicalArrivalRate;
    Modelica.Blocks.Interfaces.RealOutput reportedRate;
    Modelica.Blocks.Continuous.FirstOrder reportFilter(
      T=reportResponseTime,
      initType=Modelica.Blocks.Types.Init.InitialOutput,
      y_start=0);
  equation
    connect(physicalArrivalRate,reportFilter.u);
    connect(reportFilter.y,reportedRate);
  end FirstOrderReportFilter;
  annotation(uses(Modelica(version="4.0.0")));
end IGCInformationMolecules;

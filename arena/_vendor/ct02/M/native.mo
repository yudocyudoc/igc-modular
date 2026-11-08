within;
package ArenaCT03M
  model CT03M_18247fc54a54
    parameter Integer probe(min=1,max=4)=1;
    // Only publicly supplied experimental stimulus; molecule internals unchanged.
    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);
    IGCMolecules.AcceptedSource source0;
    IGCMolecules.BoundedQueue preparation0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue dispatch0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.DeliveryCounter receipt0;
    IGCInformationMolecules.FirstOrderReportFilter report0(reportResponseTime=1.6);
    Real dispatchRate;
    Real deliveryRate;
    Real inTransit;
    Real reportedDeliveryRate;
    Real deliveredTotal;
  equation
    connect(stimulus.y,source0.externalRate);
    connect(source0.outflow,preparation0.arrival);
    connect(preparation0.completed,dispatch0.arrival);
    connect(dispatch0.completed,receipt0.arrival);
    connect(dispatch0.completed,report0.physicalArrivalRate);
    dispatchRate=dispatch0.completed;
    deliveryRate=dispatch0.completed;
    deliveredTotal=receipt0.total;
    inTransit=0;
    reportedDeliveryRate=report0.reportedRate;
  end CT03M_18247fc54a54;

  model CT03M_2e8eb34b64cb
    parameter Integer probe(min=1,max=4)=1;
    // Only publicly supplied experimental stimulus; molecule internals unchanged.
    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);
    IGCMolecules.AcceptedSource source0;
    IGCMolecules.BoundedQueue preparation0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue dispatch0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue transit0(maxThroughput=100,responseTime=1.6);
    IGCMolecules.BoundedQueue transit1(maxThroughput=100,responseTime=1.6);
    IGCMolecules.DeliveryCounter receipt0;
    Real dispatchRate;
    Real deliveryRate;
    Real inTransit;
    Real reportedDeliveryRate;
    Real deliveredTotal;
  equation
    connect(stimulus.y,source0.externalRate);
    connect(source0.outflow,preparation0.arrival);
    connect(preparation0.completed,dispatch0.arrival);
    connect(dispatch0.completed,transit0.arrival);
    connect(transit0.completed,transit1.arrival);
    connect(transit1.completed,receipt0.arrival);
    dispatchRate=dispatch0.completed;
    deliveryRate=transit1.completed;
    deliveredTotal=receipt0.total;
    inTransit=transit0.waiting + transit1.waiting;
    reportedDeliveryRate=deliveryRate;
  end CT03M_2e8eb34b64cb;

  model CT03M_3a0c5b35e3a1
    parameter Integer probe(min=1,max=4)=1;
    // Only publicly supplied experimental stimulus; molecule internals unchanged.
    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);
    IGCMolecules.AcceptedSource source0;
    IGCMolecules.BoundedQueue preparation0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue dispatch0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue transit0(maxThroughput=100,responseTime=1.6);
    IGCMolecules.DeliveryCounter receipt0;
    IGCInformationMolecules.FirstOrderReportFilter report0(reportResponseTime=1.6);
    Real dispatchRate;
    Real deliveryRate;
    Real inTransit;
    Real reportedDeliveryRate;
    Real deliveredTotal;
  equation
    connect(stimulus.y,source0.externalRate);
    connect(source0.outflow,preparation0.arrival);
    connect(preparation0.completed,dispatch0.arrival);
    connect(dispatch0.completed,transit0.arrival);
    connect(transit0.completed,receipt0.arrival);
    connect(transit0.completed,report0.physicalArrivalRate);
    dispatchRate=dispatch0.completed;
    deliveryRate=transit0.completed;
    deliveredTotal=receipt0.total;
    inTransit=transit0.waiting;
    reportedDeliveryRate=report0.reportedRate;
  end CT03M_3a0c5b35e3a1;

  model CT03M_865c88bb0dba
    parameter Integer probe(min=1,max=4)=1;
    // Only publicly supplied experimental stimulus; molecule internals unchanged.
    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);
    IGCMolecules.AcceptedSource source0;
    IGCMolecules.BoundedQueue preparation0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue dispatch0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue transit0(maxThroughput=100,responseTime=1.6);
    IGCMolecules.BoundedQueue transit1(maxThroughput=100,responseTime=1.6);
    IGCMolecules.DeliveryCounter receipt0;
    IGCInformationMolecules.FirstOrderReportFilter report0(reportResponseTime=1.6);
    Real dispatchRate;
    Real deliveryRate;
    Real inTransit;
    Real reportedDeliveryRate;
    Real deliveredTotal;
  equation
    connect(stimulus.y,source0.externalRate);
    connect(source0.outflow,preparation0.arrival);
    connect(preparation0.completed,dispatch0.arrival);
    connect(dispatch0.completed,transit0.arrival);
    connect(transit0.completed,transit1.arrival);
    connect(transit1.completed,receipt0.arrival);
    connect(transit1.completed,report0.physicalArrivalRate);
    dispatchRate=dispatch0.completed;
    deliveryRate=transit1.completed;
    deliveredTotal=receipt0.total;
    inTransit=transit0.waiting + transit1.waiting;
    reportedDeliveryRate=report0.reportedRate;
  end CT03M_865c88bb0dba;

  model CT03M_ef5c16621e41
    parameter Integer probe(min=1,max=4)=1;
    // Only publicly supplied experimental stimulus; molecule internals unchanged.
    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);
    IGCMolecules.AcceptedSource source0;
    IGCMolecules.BoundedQueue preparation0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue dispatch0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue transit0(maxThroughput=100,responseTime=1.6);
    IGCMolecules.DeliveryCounter receipt0;
    Real dispatchRate;
    Real deliveryRate;
    Real inTransit;
    Real reportedDeliveryRate;
    Real deliveredTotal;
  equation
    connect(stimulus.y,source0.externalRate);
    connect(source0.outflow,preparation0.arrival);
    connect(preparation0.completed,dispatch0.arrival);
    connect(dispatch0.completed,transit0.arrival);
    connect(transit0.completed,receipt0.arrival);
    dispatchRate=dispatch0.completed;
    deliveryRate=transit0.completed;
    deliveredTotal=receipt0.total;
    inTransit=transit0.waiting;
    reportedDeliveryRate=deliveryRate;
  end CT03M_ef5c16621e41;

  model CT03M_f250c7b99b2c
    parameter Integer probe(min=1,max=4)=1;
    // Only publicly supplied experimental stimulus; molecule internals unchanged.
    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);
    IGCMolecules.AcceptedSource source0;
    IGCMolecules.BoundedQueue preparation0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.BoundedQueue dispatch0(maxThroughput=20,responseTime=0.5);
    IGCMolecules.DeliveryCounter receipt0;
    Real dispatchRate;
    Real deliveryRate;
    Real inTransit;
    Real reportedDeliveryRate;
    Real deliveredTotal;
  equation
    connect(stimulus.y,source0.externalRate);
    connect(source0.outflow,preparation0.arrival);
    connect(preparation0.completed,dispatch0.arrival);
    connect(dispatch0.completed,receipt0.arrival);
    dispatchRate=dispatch0.completed;
    deliveryRate=dispatch0.completed;
    deliveredTotal=receipt0.total;
    inTransit=0;
    reportedDeliveryRate=deliveryRate;
  end CT03M_f250c7b99b2c;
  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));
end ArenaCT03M;

```dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

void main() => runApp(MyApp());

class MyApp extends StatelessWidget {
 @override
 Widget build(BuildContext context) {
 return MaterialApp(
 title: 'Walking App',
 home: WalkingTracker(),
 );
 }
}


class WalkingTracker extends StatefulWidget {
 @override
 _WalkingTrackerState createState() => _WalkingTrackerState();
}

class _WalkingTrackerState extends State<WalkingTracker> {
 bool isWalking = false;
 int steps =0;
 double distance =0.0;
 int energyConsumed =0;

 @override
 Widget build(BuildContext context) {
 return Scaffold(
 appBar: AppBar(
 title: Text('Walking Tracker'),
 ),
 body: Center(
 child: Column(
 mainAxisAlignment: MainAxisAlignment.center,
 children:<Widget>[
 ElevatedButton.icon(
 onPressed: () => isWalking ? stop() : start(),
 icon: Icon(isWalking ? Icons.pause : Icons.play_arrow),
 label: Text(isWalking ? 'Stop' : 'Start'),
 ),
 SizedBox(height:20,),
 Text('Steps: $steps', style: TextStyle(fontSize:18)),
 SizedBox(height:20,),
 Text('Distance: $distance km', style: TextStyle(fontSize:18)),
 SizedBox(height:20,),
 Text('Energy Consumed: $energyConsumed kcal', style: TextStyle(fontSize:18)),
 ],
 ),
 ),
 );
 }

 void start() {
 isWalking = true;
 steps +=10; // Simulate10 steps in a walk of about1 km.
 distance =1.0 /20; // Assuming each step is0.5 meters, total distance is1 meter (or1km).
 energyConsumed +=10; // Simulating10 kcal per1 km walked.
 }

 void stop() {
 isWalking = false;
 }
}
```
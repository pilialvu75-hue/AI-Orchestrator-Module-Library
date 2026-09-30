import 'package:flutter/material.dart';

void main() {
 runApp(MyApp());
}

class MyApp extends StatelessWidget {
 @override
 Widget build(BuildContext context) {
 return MaterialApp(
 title: 'Contatore Test',
 home: CounterScreen(),
 );
 }
}

class CounterScreen extends StatefulWidget {
 @override
 _CounterScreenState createState() => _CounterScreenState();
}

class _CounterScreenState extends State<CounterScreen> {
 int counter =0;

 void incrementCounter() {
 setState(() {
 counter++;
 });
 }

 void resetCounter() {
 setState(() {
 counter =0;
 });
 }

 @override
 Widget build(BuildContext context) {
 return Scaffold(
 appBar: AppBar(
 title: Text('Contatore Test'),
 ),
 body: Center(
 child: Column(
 mainAxisAlignment: MainAxisAlignment.center,
 children:<Widget>[
 Text('$counter', style: TextStyle(fontSize:24)),
 SizedBox(height:10),
 Row(
 mainAxisAlignment: MainAxisAlignment.spaceEvenly,
 children:<Widget>[
 ElevatedButton(onPressed: incrementCounter, child: Text('+1')),
 ElevatedButton(onPressed: resetCounter, child: Text('Azzera')),
 ],
 ),
 ],
 ),
 ),
 );
 }
}
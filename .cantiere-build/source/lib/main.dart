

import 'package:flutter/material.dart';

void main() {
 runApp(MyApp());
}


class MyApp extends StatelessWidget {
 @override
 Widget build(BuildContext context) {
 return MaterialApp(
 title: 'Flutter Drawing Lessons',
 theme: ThemeData(
 primarySwatch: Colors.blue,
 ),
 home: DashboardScreen(),
 );
 }
}


class DashboardScreen extends StatefulWidget {
 @override
 _DashboardScreenState createState() => _DashboardScreenState();
}


class _DashboardScreenState extends State<DashboardScreen> {
 List<String> lessons = ['Lesson1', 'Lesson2', 'Lesson3'];
 int currentStepIndex =0;

 void navigateToNextStep() {
 setState(() {
 if (currentStepIndex< lessons.length -1) {
 currentStepIndex++;
 }
 });
 }

 @override
 Widget build(BuildContext context) {
 return Scaffold(
 appBar: AppBar(
 title: Text('Flutter Drawing Lessons'),
 ),
 body: Center(child: Column( crossAxisAlignment: CrossAxisAlignment.center, children: [ Expanded(child: ListView.builder( itemCount: lessons.length, itemBuilder: (context, index) { return ListTile( leading: Icon(Icons.menu), title: Text(lessons[index]), onTap: () {
 setState(() {
 currentStepIndex = index;
 navigateToNextStep();
 });
 }, ), ), ), Expanded(child: Container(height:500, width: double.infinity, decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20)), child: Center(child: Text('Draw here'))), ), ElevatedButton(onPressed: () {
 navigateToNextStep();
 }, child: Text('Next Step')), ])),
 );
 }
}

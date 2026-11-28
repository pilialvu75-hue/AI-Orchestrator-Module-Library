import '../../intake/utility.llm_generated.adjacent_pairs/0.1.0/payload/src/lib/adjacent_pairs.dart' as adjacent_pairs;
import '../../intake/utility.llm_generated.count_in_range/0.1.0/payload/src/lib/count_in_range.dart' as count_in_range;
import '../../intake/utility.llm_generated.cumulative_max/0.1.0/payload/src/lib/cumulative_max.dart' as cumulative_max;
import '../../intake/utility.llm_generated.first_subsequence/0.1.0/payload/src/lib/first_subsequence.dart' as first_subsequence;
import '../../intake/utility.llm_generated.fixed_chunks/0.1.0/payload/src/lib/fixed_chunks.dart' as fixed_chunks;
import '../../intake/utility.llm_generated.index_positions/0.1.0/payload/src/lib/index_positions.dart' as index_positions;
import '../../intake/utility.llm_generated.integer_frequencies/0.1.0/payload/src/lib/integer_frequencies.dart' as integer_frequencies;
import '../../intake/utility.llm_generated.interleave_lists/0.1.0/payload/src/lib/interleave_lists.dart' as interleave_lists;
import '../../intake/utility.llm_generated.intersection_unique/0.1.0/payload/src/lib/intersection_unique.dart' as intersection_unique;
import '../../intake/utility.llm_generated.max_run_length/0.1.0/payload/src/lib/max_run_length.dart' as max_run_length;
import '../../intake/utility.llm_generated.palindrome_filter/0.1.0/payload/src/lib/palindrome_filter.dart' as palindrome_filter;
import '../../intake/utility.llm_generated.rotate_left/0.1.0/payload/src/lib/rotate_left.dart' as rotate_left;
import '../../intake/utility.llm_generated.running_product/0.1.0/payload/src/lib/running_product.dart' as running_product;
import '../../intake/utility.llm_generated.stable_unique/0.1.0/payload/src/lib/stable_unique.dart' as stable_unique;
import 'dart:math';
import 'dart:convert';

void eq(Object? actual, Object? expected, String label) {
  if (actual is Map && expected is Map) {
    if (actual.length != expected.length) throw StateError('$label map length');
    for (final k in expected.keys) {
      if (!actual.containsKey(k)) throw StateError('$label missing key');
      eq(actual[k], expected[k], label);
    }
    return;
  }
  if (actual is List && expected is List) {
    if (actual.length != expected.length) throw StateError('$label length');
    for (var i=0;i<actual.length;i++) { eq(actual[i],expected[i],label); }
    return;
  }
  if (actual != expected) throw StateError('$label: $actual != $expected');
}
int referenceSearch(List<int> a,List<int> b) {
  if(b.isEmpty)return 0;
  for(var i=0;i+b.length<=a.length;i++){
    if(a.sublist(i,i+b.length).toString()==b.toString())return i;
  }
  return -1;
}
void verify(String name, List<int> a, List<int> b, int k) {
  final before=List<int>.of(a), other=List<int>.of(b);
  switch(name) {
    case 'adjacent_pairs':
      eq(adjacent_pairs.adjacentPairs(a),[for(var i=1;i<a.length;i++) [a[i-1],a[i]]],name); break;
    case 'count_in_range':
      eq(count_in_range.countInRange(a,-2,2),a.where((v)=>v>=-2&&v<=2).length,name);
      eq(count_in_range.countInRange(a,2,-2),0,name); break;
    case 'cumulative_max':
      eq(cumulative_max.cumulativeMaximum(a),[for(var i=1;i<=a.length;i++) a.take(i).reduce(max)],name); break;
    case 'first_subsequence':
      eq(first_subsequence.findSubsequence(a,b),referenceSearch(a,b),name);
      eq(first_subsequence.findSubsequence(a,[]),0,name);
      if(a.isNotEmpty){final needle=a.sublist(a.length~/2);eq(first_subsequence.findSubsequence(a,needle),referenceSearch(a,needle),name);} break;
    case 'fixed_chunks':
      final c=fixed_chunks.chunkIntegers(a,k);
      eq(c.expand((x)=>x).toList(),a,name);
      eq(c.length,(a.length+k-1)~/k,name);
      for(var i=0;i<c.length;i++){eq(c[i].length,min(k,a.length-i*k),name);} break;
    case 'index_positions':
      eq(index_positions.groupIndices(a),{for(final v in a.toSet())v:[for(var i=0;i<a.length;i++)if(a[i]==v)i]},name); break;
    case 'integer_frequencies':
      eq(integer_frequencies.countFrequencies(a),{for(final v in a.toSet())v:a.where((x)=>x==v).length},name); break;
    case 'interleave_lists':
      eq(interleave_lists.interleaveIntegers(a,b),[for(var i=0;i<max(a.length,b.length);i++)...[if(i<a.length)a[i],if(i<b.length)b[i]]],name); break;
    case 'intersection_unique':
      eq(intersection_unique.intersectStable(a,b),a.where(b.contains).toSet().toList(),name); break;
    case 'max_run_length':
      var best=0;
      for(var i=0;i<a.length;i++){var j=i;while(j<a.length&&a[j]==a[i]){j++;}best=max(best,j-i);}
      eq(max_run_length.longestRunLength(a),best,name); break;
    case 'palindrome_filter':
      final words=['','a','radar','hello','été','abba','ab','Radar',...a.map((v)=>v.toString())];
      eq(palindrome_filter.filterPalindromes(words),words.where((s)=>s==String.fromCharCodes(s.codeUnits.reversed)).toList(),name); break;
    case 'rotate_left':
      for(final steps in [0,k,-k,1000000,-1000000]){
        eq(rotate_left.rotateLeft(a,steps),a.isEmpty?<int>[]:[for(var i=0;i<a.length;i++)a[(i+steps)%a.length]],name);
      } break;
    case 'running_product':
      final bounded=a.take(12).toList();
      eq(running_product.runningProducts(bounded),[for(var i=1;i<=bounded.length;i++)bounded.take(i).fold<int>(1,(x,y)=>x*y)],name); break;
    case 'stable_unique':
      final expected=<int>[];
      for(final v in a){if(!expected.contains(v))expected.add(v);}
      eq(stable_unique.uniqueStable(a),expected,name); break;
    default: throw ArgumentError(name);
  }
  eq(a,before,'$name input unchanged');
  eq(b,other,'$name second input unchanged');
}
void main(List<String> args) {
  final names=["adjacent_pairs","count_in_range","cumulative_max","first_subsequence","fixed_chunks","index_positions","integer_frequencies","interleave_lists","intersection_unique","max_run_length","palindrome_filter","rotate_left","running_product","stable_unique"];
  final selected=args.isEmpty?names:args;
  for(final name in selected){
    final r=Random(20261128);
    final timer=Stopwatch()..start();
    for(final a in <List<int>>[[],[0],[-1],[1,1,1],[-3,-2,-1,0,1,2,3],List.filled(200,7)]){
      verify(name,a,[],1);
      verify(name,a,[1,2,1],3);
    }
    for(var i=0;i<1000;i++){
      final a=List.generate(r.nextInt(80),(_)=>r.nextInt(7)-3);
      final b=List.generate(r.nextInt(20),(_)=>r.nextInt(7)-3);
      verify(name,a,b,1+r.nextInt(100));
    }
    if(name=='fixed_chunks'){
      for(final invalid in [0,-1]){
        var rejected=false;try{fixed_chunks.chunkIntegers([1],invalid);}on ArgumentError{rejected=true;}
        eq(rejected,true,'invalid chunk size');
      }
    }
    print(jsonEncode({'module':name,'status':'PASS','random_cases':1000,'elapsed_us':timer.elapsedMicroseconds}));
  }
}

import 'dart:io';

import 'package:path/path.dart' as p;

import 'src/updater.dart';

/// Private, unique staging per update; no installation is performed here.
final class DesktopArtifactStore implements ArtifactStore {
  DesktopArtifactStore(this.stagingRoot);
  final String stagingRoot;

  @override
  Future<ArtifactWriteSession> begin(UpdateCandidate candidate) async {
    final name = candidate.artifactId;
    if (!RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$').hasMatch(name) ||
        name == '.' || name == '..') {
      throw const UpdaterFailure('Unsafe installer filename');
    }
    final root = await Directory(stagingRoot).create(recursive: true);
    final directory = await root.createTemp('update-');
    try {
      return _DesktopWriter(directory, File(p.join(directory.path, 'file.part')).openWrite(), name);
    } catch (_) {
      await directory.delete(recursive: true);
      rethrow;
    }
  }
}

final class _DesktopWriter implements ArtifactWriteSession {
  _DesktopWriter(this.directory, this.sink, this.name);
  final Directory directory;
  final IOSink sink;
  final String name;
  bool closed = false;
  bool committed = false;

  @override
  Future<void> add(List<int> bytes) async {
    if (closed) throw const UpdaterFailure('Staging already closed');
    sink.add(bytes);
  }

  @override
  Future<String> commit() async {
    if (closed) throw const UpdaterFailure('Staging already closed');
    closed = true;
    await sink.flush();
    await sink.close();
    final staged = File(p.join(directory.path, 'file.part'));
    final target = await staged.rename(p.join(directory.path, name));
    committed = true;
    return target.absolute.path;
  }

  @override
  Future<void> abort() async {
    if (committed) return;
    if (!closed) {
      closed = true;
      await sink.close();
    }
    if (await directory.exists()) await directory.delete(recursive: true);
  }
}

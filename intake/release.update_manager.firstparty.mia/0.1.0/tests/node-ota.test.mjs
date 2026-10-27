import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {
  AutoUpdateEngine, BackupManager, ModuleLoader, OTAManager, RollbackManager,
} from '../payload/src/services/mia-ota-manager/src/otaManager.js';

test('module loader accepts exact declared dependencies and rejects missing ones', () => {
  const loader = new ModuleLoader();
  assert.throws(() => loader.loadModule({
    name: 'dependent', version: '1.0.0', dependencies: ['core'],
  }), /Missing dependencies: core/);
  loader.loadModule({ name: 'core', version: '1.0.0' });
  assert.equal(loader.loadModule({
    name: 'dependent', version: '1.0.0', dependencies: ['core'],
  }).version, '1.0.0');
  assert.equal(loader.manageDependencies({ dependencies: ['core'] }), true);
  assert.equal(loader.manageDependencies({ dependencies: ['absent'] }), false);
});

test('backup archives have matching hashes and history remains bounded', () => {
  const manager = new BackupManager();
  for (let i = 0; i < 12; i++) {
    const item = manager.createBackup({ version: `1.0.${i}`, modules: [{name: 'core'}] });
    assert.equal(crypto.createHash('sha256').update(item.archive).digest('hex'), item.sha256);
  }
  assert.equal(manager.versioning().length, 10);
  assert.equal(manager.versioning()[0].version, '1.0.11');
});

test('update selection and payload digest reject older/tampered releases', () => {
  const engine = new AutoUpdateEngine();
  const releases = [{version:'v1.0.1'}, {version:'v1.0.3'}, {version:'v1.0.2'}];
  assert.equal(engine.checkUpdates('1.0.2', releases).version, 'v1.0.3');
  assert.equal(engine.checkUpdates('v1.0.3', releases), null);
  const bytes = Buffer.from('safe test payload');
  const pin = crypto.createHash('sha256').update(bytes).digest('hex');
  assert.equal(engine.verifyIntegrity(bytes, pin), true);
  assert.equal(engine.verifyIntegrity(Buffer.from('tampered payload'), pin), false);
});

test('OTA sandbox returns explicit integrity/dependency failures', async () => {
  const manager = new OTAManager();
  const noUpdate = await manager.runUpdateCycle({
    currentVersion:'2.0.0', availableUpdates:[{version:'1.0.0'}],
    downloader: async () => {throw new Error('must not download');},
    monitor: async () => {},
  });
  assert.equal(noUpdate.status, 'no-update');
  const payload = Buffer.from('fixture');
  const bundle = {version:'2.1.0', payload, sha256:'0'.repeat(64), modules:[]};
  const params = {
    currentVersion:'2.0.0', availableUpdates:[{version:'2.1.0'}],
    downloader: async () => bundle, monitor: async () => {},
  };
  assert.equal((await manager.runUpdateCycle(params)).status, 'integrity-failed');
  bundle.sha256 = crypto.createHash('sha256').update(payload).digest('hex');
  bundle.modules = [{name:'needs-core',version:'2.1.0',dependencies:['core']}];
  assert.equal((await manager.runUpdateCycle(params)).status, 'dependency-failed');
  assert.equal(manager.moduleLoader.modules.size, 0);
});

test('OTA sandbox applies verified dependency-free module with synthetic monitor', async () => {
  const manager = new OTAManager({rollbackManager:new RollbackManager()});
  const payload = Buffer.from('test-only archive');
  let monitored = '';
  const result = await manager.runUpdateCycle({
    currentVersion:'1.0.0', availableUpdates:[{version:'1.1.0'}],
    downloader: async () => ({
      version:'1.1.0', payload,
      sha256:crypto.createHash('sha256').update(payload).digest('hex'),
      modules:[{name:'example',version:'1.1.0',dependencies:[]}],
    }),
    monitor: async version => {monitored=version;},
  });
  assert.equal(result.status, 'stable');
  assert.equal(manager.moduleLoader.modules.get('example').version, '1.1.0');
  assert.equal(monitored, '1.1.0');
  assert.equal(result.backup.version,'1.1.0');
  // uploadToGithub in upstream Mia code is a stub, not a real deployment.
  assert.equal(result.release.uploaded,true);
});

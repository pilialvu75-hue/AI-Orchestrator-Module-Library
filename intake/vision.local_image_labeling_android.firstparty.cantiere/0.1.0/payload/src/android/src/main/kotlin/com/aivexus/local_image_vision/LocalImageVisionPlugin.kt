package com.aivexus.local_image_vision

import io.flutter.embedding.engine.plugins.FlutterPlugin

/** Automatically registered by Flutter; the host must NOT also register the
 * original Cantiere MainActivity channel or duplicate listeners will compete. */
class LocalImageVisionPlugin : FlutterPlugin {
    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        LocalImageVisionBridge.register(binding.applicationContext, binding.binaryMessenger)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        LocalImageVisionBridge.unregister()
    }
}

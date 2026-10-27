package com.aivexus.local_image_vision

import android.content.Context
import android.app.ActivityManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.label.ImageLabeling
import com.google.mlkit.vision.label.defaults.ImageLabelerOptions
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Offline image-category recognition. The bundled ML Kit model does not
 * contact an API, understand fine details, or run a multimodal LLM.
 * Never log image paths, labels, bytes, or user questions.
 */
internal object LocalImageVisionBridge {
    private const val channelName = "com.aiorchestrator/local_image_vision"
    private var registeredChannel: MethodChannel? = null
    private const val maxBytes = 8L * 1024 * 1024
    private const val maxDecodedEdge = 1024
    private val busy = AtomicBoolean(false)
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    fun register(context: Context, messenger: BinaryMessenger) {
        val appContext = context.applicationContext
        MethodChannel(messenger, channelName)
            .also { registeredChannel = it }
            .setMethodCallHandler { call, result ->
                if (call.method != "labelImage") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val path = call.argument<String>("path")
                if (path.isNullOrBlank()) {
                    result.error("INVALID_IMAGE", "Nessuna immagine selezionata.", null)
                    return@setMethodCallHandler
                }
                if (!busy.compareAndSet(false, true)) {
                    result.error("IMAGE_BUSY", "Analisi locale già in corso.", null)
                    return@setMethodCallHandler
                }
                worker.execute {
                    try {
                        val file = File(path)
                        if (!file.isFile || !file.canRead() ||
                            file.length() !in 1L..maxBytes) {
                            main.post {
                                busy.set(false)
                                result.error("INVALID_IMAGE", "Immagine non disponibile o oltre 8 MB.", null)
                            }
                            return@execute
                        }

                        // Refuse a new vision workload if Android is already
                        // under memory pressure. Keep the resident text model
                        // untouched; a single image is never worth an OOM crash.
                        val activityManager = appContext.getSystemService(
                            Context.ACTIVITY_SERVICE
                        ) as? ActivityManager
                        val memory = ActivityManager.MemoryInfo()
                        activityManager?.getMemoryInfo(memory)
                        if (activityManager != null &&
                            (memory.lowMemory || memory.availMem < 256L * 1024 * 1024)) {
                            main.post {
                                busy.set(false)
                                result.error(
                                    "LOCAL_VISION_MEMORY",
                                    "Memoria libera insufficiente per Image LOCAL. " +
                                        "Chiudi altre applicazioni e riprova.",
                                    null
                                )
                            }
                            return@execute
                        }

                        // Decode bounds first, then a downsampled RGB_565 bitmap
                        // to bound peak RAM on devices with small memory budgets.
                        val bounds = BitmapFactory.Options().apply {
                            inJustDecodeBounds = true
                        }
                        BitmapFactory.decodeFile(file.path, bounds)
                        val width = bounds.outWidth
                        val height = bounds.outHeight
                        if (width <= 0 || height <= 0 || width > 16384 || height > 16384) {
                            main.post {
                                busy.set(false)
                                result.error("INVALID_IMAGE", "Formato o dimensioni immagine non supportati.", null)
                            }
                            return@execute
                        }
                        var sampleSize = 1
                        while (width / sampleSize > maxDecodedEdge ||
                            height / sampleSize > maxDecodedEdge) {
                            sampleSize *= 2
                        }
                        val options = BitmapFactory.Options().apply {
                            inSampleSize = sampleSize
                            inPreferredConfig = Bitmap.Config.RGB_565
                        }
                        val bitmap = BitmapFactory.decodeFile(file.path, options)
                            ?: throw IllegalArgumentException("cannot decode image")
                        main.post {
                            val labeler = ImageLabeling.getClient(
                                ImageLabelerOptions.Builder()
                                    .setConfidenceThreshold(0.55f)
                                    .build()
                            )
                            try {
                                labeler.process(InputImage.fromBitmap(bitmap, 0))
                                    .addOnSuccessListener { labels ->
                                        val payload = labels
                                            .sortedByDescending { it.confidence }
                                            .take(5)
                                            .map {
                                                mapOf(
                                                    "label" to it.text,
                                                    "confidence" to it.confidence.toDouble()
                                                )
                                            }
                                        result.success(payload)
                                    }
                                    .addOnFailureListener {
                                        result.error(
                                            "LOCAL_VISION_FAILED",
                                            "Riconoscimento visivo locale non riuscito.",
                                            null
                                        )
                                    }
                                    .addOnCompleteListener {
                                        bitmap.recycle()
                                        labeler.close()
                                        busy.set(false)
                                    }
                            } catch (_: Exception) {
                                bitmap.recycle()
                                labeler.close()
                                busy.set(false)
                                result.error(
                                    "LOCAL_VISION_FAILED",
                                    "Riconoscimento visivo locale non riuscito.",
                                    null
                                )
                            }
                        }
                    } catch (_: OutOfMemoryError) {
                        main.post {
                            busy.set(false)
                            result.error("LOCAL_VISION_OOM", "Memoria insufficiente per analizzare la foto.", null)
                        }
                    } catch (_: Exception) {
                        main.post {
                            busy.set(false)
                            result.error("LOCAL_VISION_FAILED", "Impossibile leggere la foto sul dispositivo.", null)
                        }
                    }
                }
            }
    }

    fun unregister() {
        registeredChannel?.setMethodCallHandler(null)
        registeredChannel = null
    }
}

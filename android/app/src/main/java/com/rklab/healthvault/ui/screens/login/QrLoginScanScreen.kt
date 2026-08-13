package com.rklab.healthvault.ui.screens.login

import android.Manifest
import android.content.pm.PackageManager
import android.util.Size
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.rklab.healthvault.data.model.LoginChallengeOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.HubTeal
import com.rklab.healthvault.ui.theme.HubText
import com.rklab.healthvault.ui.theme.HubTextDim
import com.rklab.healthvault.ui.theme.Navy
import com.rklab.healthvault.ui.theme.StampRed
import com.rklab.healthvault.ui.theme.White
import com.rklab.healthvault.util.QrLoginPayload
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@Composable
fun QrLoginScanScreen(
    repository: HealthVaultRepository,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    var hasCamera by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    val askCamera = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        hasCamera = it
    }
    LaunchedEffect(Unit) {
        if (!hasCamera) askCamera.launch(Manifest.permission.CAMERA)
    }

    var scannedId by remember { mutableStateOf<String?>(null) }
    var challenge by remember { mutableStateOf<LoginChallengeOut?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var lookingUp by remember { mutableStateOf(false) }

    LaunchedEffect(scannedId) {
        val id = scannedId ?: return@LaunchedEffect
        lookingUp = true
        error = null
        runCatching { repository.getLoginChallenge(id) }
            .onSuccess { challenge = it }
            .onFailure {
                error = "This code is not for your account, or it expired."
                scannedId = null
            }
        lookingUp = false
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(HubBg)
    ) {
        if (hasCamera) {
            CameraPreview(
                modifier = Modifier.fillMaxSize(),
                enabled = scannedId == null && challenge == null,
                onCode = { raw ->
                    val id = QrLoginPayload.parse(raw)
                    if (id != null) scannedId = id
                }
            )
        }
        Column(
            modifier = Modifier
                .align(Alignment.TopStart)
                .statusBarsPadding()
                .padding(16.dp)
        ) {
            TextButton(onClick = onBack) { Text("← Back", color = HubText) }
            Text("Scan web login", color = HubText)
            Spacer(Modifier.height(4.dp))
            Text(
                "Point the camera at the QR on the website.",
                color = HubTextDim
            )
        }
        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .size(240.dp)
                .clip(RoundedCornerShape(18.dp))
                .border(2.dp, HubTeal.copy(alpha = 0.85f), RoundedCornerShape(18.dp))
        )
        Column(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            if (!hasCamera) {
                Text("Camera permission is needed to scan the code.", color = StampRed)
                Spacer(Modifier.height(10.dp))
                Button(
                    onClick = { askCamera.launch(Manifest.permission.CAMERA) },
                    colors = ButtonDefaults.buttonColors(containerColor = Navy)
                ) { Text("Allow camera", color = White) }
            } else if (lookingUp) {
                Text("Checking this sign-in…", color = HubText)
            } else if (error != null) {
                Text(error!!, color = StampRed)
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = { error = null }) { Text("Scan again", color = HubTeal) }
            } else {
                Text("Keep the website tab open after you Allow.", color = HubTextDim)
            }
        }
    }

    challenge?.let { row ->
        LoginChallengeDialog(
            repository = repository,
            challenge = row,
            onDone = {
                Toast.makeText(context, "Browser can open the vault now.", Toast.LENGTH_SHORT).show()
                challenge = null
                onBack()
            }
        )
    }
}

@Composable
private fun CameraPreview(
    modifier: Modifier,
    enabled: Boolean,
    onCode: (String) -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val executor = remember { Executors.newSingleThreadExecutor() }
    val handled = remember { AtomicBoolean(false) }
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            PreviewView(ctx).apply {
                scaleType = PreviewView.ScaleType.FILL_CENTER
            }
        },
        update = { previewView ->
            val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
            cameraProviderFuture.addListener({
                val cameraProvider = cameraProviderFuture.get()
                cameraProvider.unbindAll()
                if (!enabled) return@addListener
                handled.set(false)
                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }
                val options = BarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                    .build()
                val scanner = BarcodeScanning.getClient(options)
                val analysis = ImageAnalysis.Builder()
                    .setTargetResolution(Size(1280, 720))
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analysis.setAnalyzer(executor) { imageProxy ->
                    if (handled.get()) {
                        imageProxy.close()
                        return@setAnalyzer
                    }
                    try {
                        val image = InputImage.fromBitmap(imageProxy.toBitmap(), 0)
                        scanner.process(image)
                            .addOnSuccessListener { barcodes ->
                                val raw = barcodes.firstOrNull { it.rawValue != null }?.rawValue
                                if (raw != null && QrLoginPayload.parse(raw) != null && handled.compareAndSet(false, true)) {
                                    onCode(raw)
                                }
                            }
                            .addOnCompleteListener { imageProxy.close() }
                    } catch (_: Exception) {
                        imageProxy.close()
                    }
                }
                runCatching {
                    cameraProvider.bindToLifecycle(
                        lifecycleOwner,
                        CameraSelector.DEFAULT_BACK_CAMERA,
                        preview,
                        analysis
                    )
                }
            }, ContextCompat.getMainExecutor(context))
        }
    )
    DisposableEffect(lifecycleOwner) {
        onDispose {
            executor.shutdown()
            runCatching { ProcessCameraProvider.getInstance(context).get().unbindAll() }
        }
    }
}

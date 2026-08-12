package com.rklab.healthvault

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.rklab.healthvault.ui.navigation.HealthVaultNavGraph
import com.rklab.healthvault.ui.theme.HealthVaultTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as HealthVaultApp

        setContent {
            HealthVaultTheme {
                HealthVaultNavGraph(repository = app.repository)
            }
        }
    }
}

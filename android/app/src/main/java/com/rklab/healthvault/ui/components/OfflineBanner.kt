package com.rklab.healthvault.ui.components

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.Ink
import com.rklab.healthvault.ui.theme.InkSoft

private val BannerBg  = Color(0xFF1C1F2E)
private val BannerFg  = Color(0xFFE0E4F0)
private val PendingBg = Color(0xFF2A2330)
private val PendingFg = Color(0xFFD4A8FF)

/**
 * Slides in from the top whenever the device is offline.
 * Shows a separate pill if there are uploads queued for later.
 */
@Composable
fun OfflineBanner(isOffline: Boolean, pendingCount: Int = 0) {
    AnimatedVisibility(
        visible = isOffline,
        enter = expandVertically() + fadeIn(),
        exit  = shrinkVertically() + fadeOut()
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(BannerBg)
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Icon(
                    imageVector = Icons.Filled.CloudOff,
                    contentDescription = null,
                    tint = BannerFg,
                    modifier = Modifier.size(18.dp)
                )
                Text(
                    text = "Offline — showing cached data",
                    style = MaterialTheme.typography.labelMedium,
                    color = BannerFg,
                    modifier = Modifier.weight(1f)
                )
            }

            // Pending upload sub-banner
            AnimatedVisibility(
                visible = pendingCount > 0,
                enter = expandVertically() + fadeIn(),
                exit  = shrinkVertically() + fadeOut()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(PendingBg)
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Filled.Sync,
                        contentDescription = null,
                        tint = PendingFg,
                        modifier = Modifier.size(15.dp)
                    )
                    Text(
                        text = "$pendingCount upload${if (pendingCount == 1) "" else "s"} queued — will sync automatically",
                        style = MaterialTheme.typography.labelSmall,
                        color = PendingFg
                    )
                }
            }
        }
    }
}

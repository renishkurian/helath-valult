package com.rklab.healthvault.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.GenericShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.ui.theme.*

data class FolderDef(val category: DocCategory, val label: String, val bg: Color)

val FolderDefs = listOf(
    FolderDef(DocCategory.HOSPITAL_CARD, "Hospital Cards", Color(0xFFEFE3C4)),
    FolderDef(DocCategory.PRESCRIPTION, "Prescriptions", Color(0xFFE7EEDD)),
    FolderDef(DocCategory.LAB_REPORT, "Lab Reports", Color(0xFFEAE0EC)),
    FolderDef(DocCategory.INSURANCE, "Insurance", Color(0xFFDDE8EC)),
    FolderDef(DocCategory.VACCINATION, "Vaccination", Color(0xFFE3ECD9)),
    FolderDef(DocCategory.BILL, "Bills", Color(0xFFF1DEDA)),
    FolderDef(DocCategory.MEDICINE, "Medicines", Color(0xFFF5E9D0)),
)

private val folderTabShape = GenericShape { size, _ ->
    moveTo(0f, size.height * 0.22f)
    lineTo(size.height * 0.22f, 0f)
    lineTo(size.width, 0f)
    lineTo(size.width, size.height)
    lineTo(0f, size.height)
    close()
}

@Composable
fun FolderTab(def: FolderDef, count: Int, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .width(92.dp)
            .height(72.dp)
            .clip(folderTabShape)
            .background(def.bg)
            .clickable(onClick = onClick)
            .padding(start = 18.dp, top = 12.dp, end = 10.dp, bottom = 8.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                def.label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = Ink,
                maxLines = 2
            )
            Text(
                "%02d".format(count),
                style = MaterialTheme.typography.labelMedium,
                color = InkSoft
            )
        }
    }
}

fun docCategoryColor(category: DocCategory): Color = when (category) {
    DocCategory.HOSPITAL_CARD -> CatHospitalCard
    DocCategory.PRESCRIPTION -> CatPrescription
    DocCategory.LAB_REPORT -> CatLabReport
    DocCategory.INSURANCE -> CatInsurance
    DocCategory.VACCINATION -> CatVaccination
    DocCategory.BILL -> CatBill
    DocCategory.MEDICINE -> CatMedicine
    DocCategory.OTHER -> CatOther
}

fun docCategoryShortLabel(category: DocCategory): String = when (category) {
    DocCategory.HOSPITAL_CARD -> "ID"
    DocCategory.PRESCRIPTION -> "RX"
    DocCategory.LAB_REPORT -> "LAB"
    DocCategory.INSURANCE -> "INS"
    DocCategory.VACCINATION -> "VAX"
    DocCategory.BILL -> "BILL"
    DocCategory.MEDICINE -> "MED"
    DocCategory.OTHER -> "DOC"
}

@Composable
fun LedgerRow(
    title: String,
    metaLine: String,
    category: DocCategory,
    tagLabel: String,
    tagColor: Color,
    tagBg: Color,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(docCategoryColor(category)),
            contentAlignment = Alignment.Center
        ) {
            Text(
                docCategoryShortLabel(category),
                style = MaterialTheme.typography.labelSmall,
                color = White,
                fontWeight = FontWeight.SemiBold
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium, color = Ink, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(2.dp))
            Text(metaLine, style = MaterialTheme.typography.labelMedium, color = InkSoft)
        }
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(5.dp))
                .background(tagBg)
                .padding(horizontal = 7.dp, vertical = 3.dp)
        ) {
            Text(tagLabel, style = MaterialTheme.typography.labelSmall, color = tagColor, fontWeight = FontWeight.Medium)
        }
    }
}

@Composable
fun FamilyAvatarChip(
    name: String,
    initials: String,
    selected: Boolean,
    onClick: () -> Unit
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(64.dp).clickable(onClick = onClick)
    ) {
        Box(
            modifier = Modifier
                .size(52.dp)
                .clip(CircleShape)
                .background(if (selected) Navy else White)
                .border(1.5.dp, if (selected) Navy else LineColor, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Text(
                initials,
                style = MaterialTheme.typography.titleMedium,
                color = if (selected) White else Ink
            )
        }
        Spacer(Modifier.height(4.dp))
        Text(
            name.split(" ").first(),
            style = MaterialTheme.typography.labelSmall,
            color = if (selected) Navy else InkSoft,
            maxLines = 1
        )
    }
}

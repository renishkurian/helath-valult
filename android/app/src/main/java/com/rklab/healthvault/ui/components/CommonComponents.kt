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

data class FolderDef(val category: DocCategory, val label: String, val bg: Color, val customCategory: String? = null)

val FolderDefs = listOf(
    FolderDef(DocCategory.HOSPITAL_CARD, "Hospital Cards", CatHospitalCard),
    FolderDef(DocCategory.PRESCRIPTION, "Prescriptions", CatPrescription),
    FolderDef(DocCategory.LAB_REPORT, "Lab Reports", CatLabReport),
    FolderDef(DocCategory.INSURANCE, "Insurance", CatInsurance),
    FolderDef(DocCategory.VACCINATION, "Vaccination", CatVaccination),
    FolderDef(DocCategory.BILL, "Bills", CatBill),
    FolderDef(DocCategory.MEDICINE, "Medicines", CatMedicine),
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
    Column(
        modifier = Modifier
            .width(110.dp)
            .height(110.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(CardSurface)
            .border(1.dp, CardOutline, RoundedCornerShape(16.dp))
            .clickable(onClick = onClick)
            .padding(14.dp),
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(def.bg.copy(alpha = 0.2f)),
            contentAlignment = Alignment.Center
        ) {
            val shortLabel = if (def.customCategory != null) {
                def.customCategory.take(1).uppercase()
            } else {
                docCategoryShortLabel(def.category).take(1)
            }
            Text(
                shortLabel,
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                color = def.bg
            )
        }
        Column {
            Text(
                def.label,
                style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
                color = TextWhite,
                maxLines = 2
            )
            Spacer(Modifier.height(4.dp))
            Text(
                count.toString(),
                style = MaterialTheme.typography.labelSmall,
                color = TextGray
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
    tagColor: Color = Sage,
    tagBg: Color = SageBg,
    onClick: () -> Unit,
    trailingAction: (@Composable () -> Unit)? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(CardSurface)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(docCategoryColor(category).copy(alpha = 0.22f)),
            contentAlignment = Alignment.Center
        ) {
            Text(
                docCategoryShortLabel(category),
                style = MaterialTheme.typography.labelSmall,
                color = docCategoryColor(category),
                fontWeight = FontWeight.Bold
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                title,
                style = MaterialTheme.typography.bodyMedium,
                color = TextWhite,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1
            )
            Spacer(Modifier.height(3.dp))
            Text(
                metaLine,
                style = MaterialTheme.typography.labelMedium,
                color = TextGray,
                maxLines = 1
            )
        }
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(8.dp))
                .background(SageBg)
                .padding(horizontal = 10.dp, vertical = 6.dp)
        ) {
            Text(tagLabel, style = MaterialTheme.typography.labelSmall, color = Sage, fontWeight = FontWeight.SemiBold)
        }
        if (trailingAction != null) {
            Spacer(Modifier.width(2.dp))
            trailingAction()
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
        val boxModifier = if (selected) {
            Modifier
                .size(52.dp)
                .clip(CircleShape)
                .background(GradientPrimary)
        } else {
            Modifier
                .size(52.dp)
                .clip(CircleShape)
                .background(Color.Transparent)
                .border(1.dp, CardOutline, CircleShape)
        }

        Box(
            modifier = boxModifier,
            contentAlignment = Alignment.Center
        ) {
            Text(
                initials,
                style = MaterialTheme.typography.titleMedium,
                color = if (selected) TextWhite else TextGray
            )
        }
        Spacer(Modifier.height(8.dp))
        Text(
            name.split(" ").first(),
            style = MaterialTheme.typography.labelSmall,
            color = if (selected) TextWhite else TextGray,
            maxLines = 1
        )
    }
}

package com.rklab.healthvault.ui.screens.search

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.rklab.healthvault.data.model.CardOut
import com.rklab.healthvault.data.model.DocumentOut
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.HealthIdCard
import com.rklab.healthvault.ui.components.LedgerRow
import com.rklab.healthvault.ui.theme.*
import com.rklab.healthvault.util.ViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class SearchUiState(
    val query: String = "",
    val loading: Boolean = false,
    val cards: List<CardOut> = emptyList(),
    val documents: List<DocumentOut> = emptyList()
)

class SearchViewModel(private val repository: HealthVaultRepository) : ViewModel() {
    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state

    fun search(query: String) {
        _state.value = _state.value.copy(query = query)
        if (query.isBlank()) {
            _state.value = _state.value.copy(cards = emptyList(), documents = emptyList())
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true)
            try {
                val result = repository.search(query)
                _state.value = _state.value.copy(loading = false, cards = result.cards, documents = result.documents)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false)
            }
        }
    }
}

@Composable
fun SearchScreen(repository: HealthVaultRepository) {
    val viewModel: SearchViewModel = viewModel(factory = ViewModelFactory(repository))
    val state by viewModel.state.collectAsState()

    Column(modifier = Modifier.fillMaxSize().background(Paper).padding(20.dp)) {
        Text("SEARCH", style = MaterialTheme.typography.labelMedium, color = InkSoft)
        Spacer(Modifier.height(4.dp))
        Text("Find a card or document", style = MaterialTheme.typography.headlineMedium, color = Ink)
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = state.query,
            onValueChange = { viewModel.search(it) },
            placeholder = { Text("Search by hospital name…") },
            leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null, tint = InkSoft) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(18.dp))

        if (state.loading) {
            CircularProgressIndicator(color = Navy)
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = PaddingValues(bottom = 100.dp)) {
            if (state.cards.isNotEmpty()) {
                item { Text("HOSPITAL CARDS", style = MaterialTheme.typography.labelMedium, color = InkSoft) }
                items(state.cards) { card ->
                    HealthIdCard(card = card, patientName = "", modifier = Modifier.fillMaxWidth())
                }
            }
            if (state.documents.isNotEmpty()) {
                item { Text("DOCUMENTS", style = MaterialTheme.typography.labelMedium, color = InkSoft) }
                item {
                    Column(
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(White)
                    ) {
                        state.documents.forEach { doc ->
                            LedgerRow(
                                title = doc.title,
                                metaLine = "${doc.doc_date ?: doc.created_at.take(10)} · ${doc.hospital_name ?: "—"}",
                                category = doc.category,
                                tagLabel = "Open",
                                tagColor = Sage,
                                tagBg = SageBg,
                                onClick = {}
                            )
                            Divider(color = PaperDeep, thickness = 1.dp)
                        }
                    }
                }
            }
            if (state.query.isNotBlank() && !state.loading && state.cards.isEmpty() && state.documents.isEmpty()) {
                item { Text("No matches for \"${state.query}\".", color = InkSoft) }
            }
        }
    }
}

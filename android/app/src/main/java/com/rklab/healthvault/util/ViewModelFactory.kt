package com.rklab.healthvault.util

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.rklab.healthvault.data.repository.HealthVaultRepository

class ViewModelFactory(private val repository: HealthVaultRepository) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return modelClass.getConstructor(HealthVaultRepository::class.java).newInstance(repository)
    }
}

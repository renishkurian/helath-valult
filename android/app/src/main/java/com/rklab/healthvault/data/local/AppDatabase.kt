package com.rklab.healthvault.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [
        PersonEntity::class,
        CardEntity::class,
        DocumentEntity::class,
        ReminderEntity::class,
        PendingUploadEntity::class
    ],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun personDao(): PersonDao
    abstract fun cardDao(): CardDao
    abstract fun documentDao(): DocumentDao
    abstract fun reminderDao(): ReminderDao
    abstract fun pendingUploadDao(): PendingUploadDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "healthvault.db"
                ).fallbackToDestructiveMigration().build().also { INSTANCE = it }
            }
    }
}

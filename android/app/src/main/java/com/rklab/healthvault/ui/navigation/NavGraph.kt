package com.rklab.healthvault.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.HealthVaultBottomNav
import com.rklab.healthvault.ui.components.MainTab
import com.rklab.healthvault.ui.screens.cards.CardListScreen
import com.rklab.healthvault.ui.screens.documents.DocumentListScreen
import com.rklab.healthvault.ui.screens.documents.UploadDocumentScreen
import com.rklab.healthvault.ui.screens.family.FamilyScreen
import com.rklab.healthvault.ui.screens.home.HomeScreen
import com.rklab.healthvault.ui.screens.login.LoginScreen
import com.rklab.healthvault.ui.screens.reminders.RemindersScreen
import com.rklab.healthvault.ui.screens.search.SearchScreen
import com.rklab.healthvault.ui.screens.server.ServerSetupScreen
import com.rklab.healthvault.ui.screens.settings.SettingsScreen
import kotlinx.coroutines.flow.first

private object Routes {
    const val SERVER_SETUP = "server_setup"
    const val LOGIN = "login"
    const val HOME = "home"
    const val SEARCH = "search"
    const val REMINDERS = "reminders"
    const val FAMILY = "family"
    const val SETTINGS = "settings"
    const val AUDIT = "audit"
    const val CARDS = "cards/{personId}/{personName}"
    const val DOCUMENTS = "documents/{personId}?category={category}&custom_category={custom_category}&label={label}"
    const val UPLOAD = "upload/{personId}?category={category}&camera={camera}"
    const val VIEWER = "viewer/{docId}?fileId={fileId}"
    const val EDIT = "edit/{docId}"

    fun cards(personId: String, personName: String) = "cards/$personId/$personName"
    fun documents(personId: String, category: DocCategory?, customCategory: String?) =
        "documents/$personId?category=${category?.name ?: ""}&custom_category=${customCategory ?: ""}&label=${customCategory ?: category?.name ?: "Documents"}"
    fun upload(personId: String, category: DocCategory?, camera: Boolean = false) =
        "upload/$personId?category=${category?.name ?: ""}&camera=${if (camera) "1" else "0"}"
    fun viewer(docId: String, fileId: String?) = "viewer/$docId?fileId=${fileId ?: ""}"
    fun edit(docId: String) = "edit/$docId"
}

@Composable
fun HealthVaultNavGraph(repository: HealthVaultRepository) {
    val navController = rememberNavController()
    var startDestination by remember { mutableStateOf<String?>(null) }
    var isViewer by remember { mutableStateOf(repository.isViewer) }
    val context = LocalContext.current

    LaunchedEffect(Unit) {
        startDestination = when {
            !repository.isServerConfigured() -> Routes.SERVER_SETUP
            !repository.isLoggedIn -> Routes.LOGIN
            else -> Routes.HOME
        }
        if (repository.isLoggedIn) {
            runCatching { repository.me() }
            isViewer = repository.isViewer
        }
    }

    val start = startDestination ?: return

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val mainTabs = setOf(Routes.HOME, Routes.SEARCH, Routes.REMINDERS, Routes.FAMILY)

    Scaffold(
        bottomBar = {
            if (currentRoute in mainTabs) {
                val current = when (currentRoute) {
                    Routes.SEARCH -> MainTab.SEARCH
                    Routes.REMINDERS -> MainTab.REMINDERS
                    Routes.FAMILY -> MainTab.FAMILY
                    else -> MainTab.HOME
                }
                HealthVaultBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        MainTab.HOME -> Routes.HOME
                        MainTab.SEARCH -> Routes.SEARCH
                        MainTab.REMINDERS -> Routes.REMINDERS
                        MainTab.FAMILY -> Routes.FAMILY
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.HOME) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = start,
            modifier = Modifier.padding(padding)
        ) {
            composable(Routes.SERVER_SETUP) {
                ServerSetupScreen(repository = repository) {
                    val next = if (repository.isLoggedIn) Routes.HOME else Routes.LOGIN
                    navController.navigate(next) { popUpTo(Routes.SERVER_SETUP) { inclusive = true } }
                }
            }

            composable(Routes.LOGIN) {
                LoginScreen(
                    repository = repository,
                    onAuthenticated = {
                        isViewer = repository.isViewer
                        com.rklab.healthvault.util.ReminderScheduler.rescheduleAll(context)
                        navController.navigate(Routes.HOME) { popUpTo(Routes.LOGIN) { inclusive = true } }
                    },
                    onChangeServer = { navController.navigate(Routes.SERVER_SETUP) }
                )
            }

            composable(Routes.SETTINGS) {
                SettingsScreen(
                    repository = repository,
                    onBack = { navController.popBackStack() },
                    onLoggedOut = {
                        navController.navigate(Routes.LOGIN) { popUpTo(0) { inclusive = true } }
                    },
                    onOpenAuditLog = { navController.navigate(Routes.AUDIT) }
                )
            }

            composable(Routes.AUDIT) {
                com.rklab.healthvault.ui.screens.audit.AuditLogScreen(
                    repository = repository,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.HOME) {
                val ctx = LocalContext.current
                LaunchedEffect(Unit) {
                    val app = ctx.applicationContext as com.rklab.healthvault.HealthVaultApp
                    if (app.pendingQuickAdd) {
                        app.pendingQuickAdd = false
                        val pid = repository.activePersonFlow().first()
                            ?: repository.listPeople().firstOrNull()?.id
                        if (!pid.isNullOrBlank() && !repository.isViewer) {
                            navController.navigate(Routes.upload(pid, DocCategory.HOSPITAL_CARD, camera = true))
                        }
                    }
                }
                HomeScreen(
                    repository = repository,
                    onAddFamily = { navController.navigate(Routes.FAMILY) },
                    onOpenFolder = { personId, category, customCategory ->
                        navController.navigate(Routes.documents(personId, category, customCategory))
                    },
                    onAddDocument = { personId ->
                        navController.navigate(Routes.upload(personId, null))
                    },
                    onOpenDocument = { doc, fileId -> 
                        navController.navigate(Routes.viewer(doc.id, fileId))
                    },
                    onAddCard = { navController.navigate(Routes.FAMILY) },
                    onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                    isViewer = isViewer
                )
            }

            composable(Routes.SEARCH) {
                SearchScreen(
                    repository = repository,
                    onOpenDocument = { doc -> navController.navigate(Routes.viewer(doc.id, null)) }
                )
            }

            composable(Routes.REMINDERS) {
                var activePersonId by remember { mutableStateOf<String?>(null) }
                LaunchedEffect(Unit) { activePersonId = repository.activePersonFlow().first() }
                RemindersScreen(repository = repository, activePersonId = activePersonId)
            }

            composable(Routes.FAMILY) {
                FamilyScreen(repository = repository) { person ->
                    navController.navigate(Routes.cards(person.id, person.name))
                }
            }

            composable(
                Routes.CARDS,
                arguments = listOf(
                    navArgument("personId") { type = NavType.StringType },
                    navArgument("personName") { type = NavType.StringType }
                )
            ) { entry ->
                val personId = entry.arguments?.getString("personId") ?: return@composable
                val personName = entry.arguments?.getString("personName") ?: ""
                CardListScreen(
                    repository = repository,
                    personId = personId,
                    personName = personName,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(
                Routes.DOCUMENTS,
                arguments = listOf(
                    navArgument("personId") { type = NavType.StringType },
                    navArgument("category") { type = NavType.StringType; nullable = true; defaultValue = "" },
                    navArgument("custom_category") { type = NavType.StringType; nullable = true; defaultValue = "" },
                    navArgument("label") { type = NavType.StringType; defaultValue = "" }
                )
            ) { entry ->
                val personId = entry.arguments?.getString("personId").orEmpty()
                val categoryStr = entry.arguments?.getString("category").orEmpty()
                val category = categoryStr.takeIf { it.isNotBlank() }?.let { DocCategory.valueOf(it) }
                val customCategory = entry.arguments?.getString("custom_category")?.takeIf { it.isNotBlank() }
                val label = entry.arguments?.getString("label") ?: "Documents"

                var resolvedPersonId by remember { mutableStateOf(personId) }
                LaunchedEffect(Unit) {
                    if (resolvedPersonId.isBlank()) {
                        resolvedPersonId = repository.activePersonFlow().first().orEmpty()
                    }
                }
                if (resolvedPersonId.isNotBlank()) {
                    DocumentListScreen(
                        repository = repository,
                        personId = resolvedPersonId,
                        category = category,
                        customCategory = customCategory,
                        title = label,
                        onBack = { navController.popBackStack() },
                        onAddDocument = { navController.navigate(Routes.upload(resolvedPersonId, category)) },
                        onOpenFile = { docId, fileId -> navController.navigate(Routes.viewer(docId, fileId)) },
                        onEditDocument = { docId -> navController.navigate(Routes.edit(docId)) }
                    )
                }
            }

            composable(
                Routes.VIEWER,
                arguments = listOf(
                    navArgument("docId") { type = NavType.StringType },
                    navArgument("fileId") { type = NavType.StringType; nullable = true; defaultValue = "" }
                )
            ) { entry ->
                val docId = entry.arguments?.getString("docId").orEmpty()
                val fileId = entry.arguments?.getString("fileId")?.takeIf { it.isNotBlank() }
                
                com.rklab.healthvault.ui.screens.documents.DocumentViewerScreen(
                    repository = repository,
                    docId = docId,
                    fileId = fileId,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(
                Routes.UPLOAD,
                arguments = listOf(
                    navArgument("personId") { type = NavType.StringType },
                    navArgument("category") { type = NavType.StringType; nullable = true; defaultValue = "" },
                    navArgument("camera") { type = NavType.StringType; nullable = true; defaultValue = "0" }
                )
            ) { entry ->
                val personId = entry.arguments?.getString("personId").orEmpty()
                val categoryStr = entry.arguments?.getString("category").orEmpty()
                val category = categoryStr.takeIf { it.isNotBlank() }?.let { DocCategory.valueOf(it) }
                val autoCamera = entry.arguments?.getString("camera") == "1"

                var resolvedPersonId by remember { mutableStateOf(personId) }
                LaunchedEffect(Unit) {
                    if (resolvedPersonId.isBlank()) {
                        // Try DataStore first; if still empty (e.g. first login before HomeViewModel
                        // has written it), fall back to the first person from the API.
                        val fromStore = repository.activePersonFlow().first().orEmpty()
                        resolvedPersonId = if (fromStore.isNotBlank()) {
                            fromStore
                        } else {
                            repository.listPeople().firstOrNull()?.id.orEmpty()
                        }
                    }
                }
                if (resolvedPersonId.isNotBlank()) {
                    UploadDocumentScreen(
                        repository = repository,
                        personId = resolvedPersonId,
                        defaultCategory = category,
                        autoOpenCamera = autoCamera,
                        onDone = { navController.popBackStack() },
                        onBack = { navController.popBackStack() }
                    )
                }
            }

            composable(
                Routes.EDIT,
                arguments = listOf(
                    navArgument("docId") { type = NavType.StringType }
                )
            ) { entry ->
                val docId = entry.arguments?.getString("docId").orEmpty()
                com.rklab.healthvault.ui.screens.documents.EditDocumentScreen(
                    repository = repository,
                    docId = docId,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() }
                )
            }
        }
    }
}

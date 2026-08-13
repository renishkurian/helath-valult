package com.rklab.healthvault.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import com.rklab.healthvault.ui.theme.HubBg
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import com.rklab.healthvault.data.model.DocCategory
import com.rklab.healthvault.data.repository.HealthVaultRepository
import com.rklab.healthvault.ui.components.HealthVaultBottomNav
import com.rklab.healthvault.ui.components.MainTab
import com.rklab.healthvault.ui.components.PasswordTab
import com.rklab.healthvault.ui.components.PasswordVaultBottomNav
import com.rklab.healthvault.ui.components.FinanceTab
import com.rklab.healthvault.ui.components.FinanceBottomNav
import com.rklab.healthvault.ui.components.LockerTab
import com.rklab.healthvault.ui.components.LockerBottomNav
import com.rklab.healthvault.ui.components.UrlTab
import com.rklab.healthvault.ui.components.UrlBottomNav
import com.rklab.healthvault.ui.screens.finance.*
import com.rklab.healthvault.ui.screens.locker.*
import com.rklab.healthvault.ui.screens.urls.*
import com.rklab.healthvault.ui.screens.passwords.*
import com.rklab.healthvault.ui.screens.shell.ModulePickerScreen
import com.rklab.healthvault.ui.screens.cards.CardListScreen
import com.rklab.healthvault.ui.screens.documents.DocumentListScreen
import com.rklab.healthvault.ui.screens.documents.UploadDocumentScreen
import com.rklab.healthvault.ui.screens.family.FamilyScreen
import com.rklab.healthvault.ui.screens.home.HomeScreen
import com.rklab.healthvault.ui.screens.login.LoginScreen
import com.rklab.healthvault.ui.screens.login.QrLoginScanScreen
import com.rklab.healthvault.ui.screens.reminders.RemindersScreen
import com.rklab.healthvault.ui.screens.search.SearchScreen
import com.rklab.healthvault.ui.screens.server.ServerSetupScreen
import com.rklab.healthvault.ui.screens.settings.SettingsScreen
import com.rklab.healthvault.ui.screens.login.LoginChallengeDialog
import com.rklab.healthvault.data.model.LoginChallengeOut
import com.rklab.healthvault.util.LoginChallengeNotifier
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first

private object Routes {
    const val SERVER_SETUP = "server_setup"
    const val LOGIN = "login"
    const val MODULES = "modules"
    const val HOME = "home"
    const val VAULT = "vault"
    const val VAULT_GENERATOR = "vault_generator"
    const val VAULT_HEALTH = "vault_health"
    const val VAULT_SENDS = "vault_sends?itemId={itemId}"
    const val VAULT_TRASH = "vault_trash"
    const val VAULT_ITEM = "vault_item/{itemId}"
    const val VAULT_EDIT = "vault_edit?itemId={itemId}&type={type}"
    const val FINANCE = "finance"
    const val FINANCE_STATS = "finance_stats"
    const val FINANCE_ACCOUNTS = "finance_accounts"
    const val FINANCE_MORE = "finance_more"
    const val FINANCE_ADD = "finance_add?accountId={accountId}"
    const val FINANCE_ACCOUNT = "finance_account/{accountId}"
    const val FINANCE_INBOX = "finance_inbox"
    const val FINANCE_EMI = "finance_emi"
    const val LOCKER = "locker"
    const val LOCKER_EXPIRING = "locker_expiring"
    const val LOCKER_ADD = "locker_add?type={type}"
    const val LOCKER_ITEM = "locker_item/{itemId}"
    const val URLS = "urls"
    const val URLS_FAVORITES = "urls_favorites"
    const val URLS_MANAGE = "urls_manage"
    const val URLS_ADD = "urls_add?categoryId={categoryId}"
    const val URLS_ITEM = "urls_item/{itemId}"

    fun lockerAdd(type: String? = null) = "locker_add?type=${type ?: ""}"
    fun lockerItem(itemId: String) = "locker_item/$itemId"
    fun urlsAdd(categoryId: String? = null) = "urls_add?categoryId=${categoryId ?: ""}"
    fun urlsItem(itemId: String) = "urls_item/$itemId"

    fun financeAdd(accountId: String? = null) = "finance_add?accountId=${accountId ?: ""}"
    fun financeAccount(accountId: String) = "finance_account/$accountId"

    fun vaultSends(itemId: String? = null) = "vault_sends?itemId=${itemId ?: ""}"
    fun vaultItem(itemId: String) = "vault_item/$itemId"
    fun vaultEdit(itemId: String? = null, type: String = "login") =
        "vault_edit?itemId=${itemId ?: ""}&type=$type"
    const val SEARCH = "search"
    const val REMINDERS = "reminders"
    const val CARE = "care"
    const val FAMILY = "family"
    const val SETTINGS = "settings"
    const val QR_SCAN = "qr_scan"
    const val AUDIT = "audit"
    const val SHARES = "shares"
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
            else -> Routes.MODULES
        }
        if (repository.isLoggedIn) {
            runCatching { repository.me() }
            isViewer = repository.isViewer
        }
    }

    val start = startDestination ?: return

    var pendingWebLogin by remember { mutableStateOf<LoginChallengeOut?>(null) }
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(repository.isLoggedIn, start, lifecycleOwner) {
        if (!repository.isLoggedIn || start == Routes.LOGIN || start == Routes.SERVER_SETUP) {
            pendingWebLogin = null
            return@LaunchedEffect
        }
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                runCatching {
                    val next = repository.pendingLoginChallenges().firstOrNull()
                    pendingWebLogin = next
                    if (next != null) LoginChallengeNotifier.show(context, next)
                }
                delay(2_000)
            }
        }
    }

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val mainTabs = setOf(Routes.HOME, Routes.SEARCH, Routes.CARE, Routes.REMINDERS, Routes.FAMILY)
    val passwordTabs = setOf(Routes.VAULT, Routes.VAULT_GENERATOR, Routes.VAULT_HEALTH, "vault_sends?itemId={itemId}")
    val financeTabs = setOf(Routes.FINANCE, Routes.FINANCE_STATS, Routes.FINANCE_ACCOUNTS, Routes.FINANCE_MORE)
    val lockerTabs = setOf(Routes.LOCKER, Routes.LOCKER_EXPIRING)
    val urlTabs = setOf(Routes.URLS, Routes.URLS_FAVORITES, Routes.URLS_MANAGE)
    val onFinanceAccount = currentRoute?.startsWith("finance_account/") == true
    val onLockerItem = currentRoute?.startsWith("locker_item/") == true
    val onLockerAdd = currentRoute?.startsWith("locker_add") == true
    val onUrlItem = currentRoute?.startsWith("urls_item/") == true
    val onUrlAdd = currentRoute?.startsWith("urls_add") == true

    Scaffold(
        containerColor = if (currentRoute == Routes.MODULES) HubBg else MaterialTheme.colorScheme.background,
        bottomBar = {
            if (currentRoute in lockerTabs || onLockerItem || onLockerAdd) {
                val current = if (currentRoute == Routes.LOCKER_EXPIRING) LockerTab.EXPIRING else LockerTab.LOCKER
                LockerBottomNav(current = current) { tab ->
                    val route = if (tab == LockerTab.EXPIRING) Routes.LOCKER_EXPIRING else Routes.LOCKER
                    navController.navigate(route) {
                        popUpTo(Routes.LOCKER) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in urlTabs || onUrlItem || onUrlAdd) {
                val current = when (currentRoute) {
                    Routes.URLS_FAVORITES -> UrlTab.FAVORITES
                    Routes.URLS_MANAGE -> UrlTab.MANAGE
                    else -> UrlTab.LINKS
                }
                UrlBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        UrlTab.LINKS -> Routes.URLS
                        UrlTab.FAVORITES -> Routes.URLS_FAVORITES
                        UrlTab.MANAGE -> Routes.URLS_MANAGE
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.URLS) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in financeTabs || onFinanceAccount) {
                val current = when {
                    currentRoute == Routes.FINANCE_STATS -> FinanceTab.STATS
                    currentRoute == Routes.FINANCE_ACCOUNTS || onFinanceAccount -> FinanceTab.ACCOUNTS
                    currentRoute == Routes.FINANCE_MORE -> FinanceTab.MORE
                    else -> FinanceTab.TRANS
                }
                FinanceBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        FinanceTab.TRANS -> Routes.FINANCE
                        FinanceTab.STATS -> Routes.FINANCE_STATS
                        FinanceTab.ACCOUNTS -> Routes.FINANCE_ACCOUNTS
                        FinanceTab.MORE -> Routes.FINANCE_MORE
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.FINANCE) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in passwordTabs || currentRoute?.startsWith("vault_sends") == true) {
                val current = when {
                    currentRoute == Routes.VAULT_GENERATOR -> PasswordTab.GENERATOR
                    currentRoute == Routes.VAULT_HEALTH -> PasswordTab.HEALTH
                    currentRoute?.startsWith("vault_sends") == true -> PasswordTab.SEND
                    else -> PasswordTab.VAULT
                }
                PasswordVaultBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        PasswordTab.VAULT -> Routes.VAULT
                        PasswordTab.GENERATOR -> Routes.VAULT_GENERATOR
                        PasswordTab.SEND -> Routes.vaultSends()
                        PasswordTab.HEALTH -> Routes.VAULT_HEALTH
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.VAULT) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in mainTabs) {
                val current = when (currentRoute) {
                    Routes.SEARCH -> MainTab.SEARCH
                    Routes.CARE -> MainTab.CARE
                    Routes.REMINDERS -> MainTab.REMINDERS
                    Routes.FAMILY -> MainTab.FAMILY
                    else -> MainTab.HOME
                }
                HealthVaultBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        MainTab.HOME -> Routes.HOME
                        MainTab.SEARCH -> Routes.SEARCH
                        MainTab.CARE -> Routes.CARE
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
            modifier = if (currentRoute == Routes.MODULES) Modifier else Modifier.padding(padding)
        ) {
            composable(Routes.SERVER_SETUP) {
                ServerSetupScreen(repository = repository) {
                    val next = if (repository.isLoggedIn) Routes.MODULES else Routes.LOGIN
                    navController.navigate(next) { popUpTo(Routes.SERVER_SETUP) { inclusive = true } }
                }
            }

            composable(Routes.LOGIN) {
                LoginScreen(
                    repository = repository,
                    onAuthenticated = {
                        isViewer = repository.isViewer
                        com.rklab.healthvault.util.ReminderScheduler.rescheduleAll(context)
                        com.rklab.healthvault.util.EmiScheduler.rescheduleAll(context)
                        navController.navigate(Routes.MODULES) { popUpTo(Routes.LOGIN) { inclusive = true } }
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
                    onOpenAuditLog = { navController.navigate(Routes.AUDIT) },
                    onOpenShareHistory = { navController.navigate(Routes.SHARES) },
                    onOpenModules = { navController.navigate(Routes.MODULES) { popUpTo(Routes.MODULES) { inclusive = false } } },
                    onScanQr = { navController.navigate(Routes.QR_SCAN) }
                )
            }

            composable(Routes.QR_SCAN) {
                QrLoginScanScreen(
                    repository = repository,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.MODULES) {
                ModulePickerScreen(
                    repository = repository,
                    onHealth = {
                        navController.navigate(Routes.HOME) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    },
                    onPasswords = {
                        navController.navigate(Routes.VAULT) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    },
                    onFinance = {
                        navController.navigate(Routes.FINANCE) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    },
                    onLocker = {
                        navController.navigate(Routes.LOCKER) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    },
                    onUrls = {
                        navController.navigate(Routes.URLS) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    },
                    onSettings = { navController.navigate(Routes.SETTINGS) },
                    onScanQr = { navController.navigate(Routes.QR_SCAN) },
                    onVaultHealth = {
                        navController.navigate(Routes.VAULT_HEALTH) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    }
                )
            }

            composable(Routes.LOCKER) {
                LockerListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.lockerItem(it)) },
                    onAdd = { navController.navigate(Routes.lockerAdd(it)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.LOCKER_EXPIRING) {
                LockerListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.lockerItem(it)) },
                    onAdd = { navController.navigate(Routes.lockerAdd(it)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    expiringOnly = true
                )
            }
            composable(
                Routes.LOCKER_ADD,
                arguments = listOf(navArgument("type") { type = NavType.StringType; defaultValue = "" })
            ) { entry ->
                val type = entry.arguments?.getString("type").orEmpty().ifBlank { null }
                LockerAddScreen(
                    repository = repository,
                    defaultType = type,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() }
                )
            }
            composable(
                Routes.LOCKER_ITEM,
                arguments = listOf(navArgument("itemId") { type = NavType.StringType })
            ) { entry ->
                LockerItemScreen(
                    repository = repository,
                    itemId = entry.arguments?.getString("itemId").orEmpty(),
                    onBack = { navController.popBackStack() }
                )
            }
            composable(Routes.URLS) {
                UrlListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.urlsItem(it)) },
                    onAdd = { navController.navigate(Routes.urlsAdd(it)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.URLS_FAVORITES) {
                UrlListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.urlsItem(it)) },
                    onAdd = { navController.navigate(Routes.urlsAdd(it)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    favoritesOnly = true
                )
            }
            composable(Routes.URLS_MANAGE) {
                UrlManageScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(
                Routes.URLS_ADD,
                arguments = listOf(navArgument("categoryId") { type = NavType.StringType; defaultValue = "" })
            ) { entry ->
                val categoryId = entry.arguments?.getString("categoryId").orEmpty().ifBlank { null }
                UrlAddScreen(
                    repository = repository,
                    defaultCategoryId = categoryId,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() }
                )
            }
            composable(
                Routes.URLS_ITEM,
                arguments = listOf(navArgument("itemId") { type = NavType.StringType })
            ) { entry ->
                UrlItemScreen(
                    repository = repository,
                    itemId = entry.arguments?.getString("itemId").orEmpty(),
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.FINANCE) {
                FinanceTransScreen(
                    repository = repository,
                    onAdd = { navController.navigate(Routes.financeAdd()) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.FINANCE_STATS) { FinanceStatsScreen(repository) }
            composable(Routes.FINANCE_ACCOUNTS) {
                FinanceAccountsScreen(repository) { id -> navController.navigate(Routes.financeAccount(id)) }
            }
            composable(
                Routes.FINANCE_ACCOUNT,
                arguments = listOf(navArgument("accountId") { type = NavType.StringType })
            ) { entry ->
                val id = entry.arguments?.getString("accountId") ?: return@composable
                FinanceAccountDetailScreen(
                    repository = repository,
                    accountId = id,
                    onBack = { navController.popBackStack() },
                    onAdd = { accId -> navController.navigate(Routes.financeAdd(accId)) }
                )
            }
            composable(Routes.FINANCE_MORE) {
                FinanceMoreScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    onOpenInbox = { navController.navigate(Routes.FINANCE_INBOX) },
                    onOpenEmi = { navController.navigate(Routes.FINANCE_EMI) }
                )
            }
            composable(Routes.FINANCE_EMI) {
                FinanceEmiScreen(repository) { navController.popBackStack() }
            }
            composable(
                Routes.FINANCE_ADD,
                arguments = listOf(navArgument("accountId") { type = NavType.StringType; nullable = true; defaultValue = "" })
            ) { entry ->
                val prefill = entry.arguments?.getString("accountId")?.takeIf { it.isNotBlank() }
                FinanceAddScreen(
                    repository = repository,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() },
                    prefillAccountId = prefill
                )
            }
            composable(Routes.FINANCE_INBOX) {
                FinanceInboxScreen(repository) { navController.popBackStack() }
            }
            composable(Routes.VAULT) {
                VaultListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.vaultItem(it)) },
                    onAddItem = { type -> navController.navigate(Routes.vaultEdit(type = type)) },
                    onOpenTrash = { navController.navigate(Routes.VAULT_TRASH) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.VAULT_GENERATOR) { GeneratorScreen(repository) }
            composable(Routes.VAULT_HEALTH) {
                VaultHealthScreen(repository) { navController.navigate(Routes.vaultItem(it)) }
            }
            composable(
                Routes.VAULT_SENDS,
                arguments = listOf(navArgument("itemId") { type = NavType.StringType; nullable = true; defaultValue = "" })
            ) { entry ->
                val itemId = entry.arguments?.getString("itemId")?.takeIf { it.isNotBlank() }
                VaultSendsScreen(repository, prefillItemId = itemId)
            }
            composable(Routes.VAULT_TRASH) {
                VaultTrashScreen(repository, onBack = { navController.popBackStack() })
            }
            composable(
                Routes.VAULT_ITEM,
                arguments = listOf(navArgument("itemId") { type = NavType.StringType })
            ) { entry ->
                val itemId = entry.arguments?.getString("itemId").orEmpty()
                VaultItemScreen(
                    repository = repository,
                    itemId = itemId,
                    onBack = { navController.popBackStack() },
                    onEdit = { navController.navigate(Routes.vaultEdit(itemId)) },
                    onSend = { navController.navigate(Routes.vaultSends(itemId)) }
                )
            }
            composable(
                Routes.VAULT_EDIT,
                arguments = listOf(
                    navArgument("itemId") { type = NavType.StringType; nullable = true; defaultValue = "" },
                    navArgument("type") { type = NavType.StringType; defaultValue = "login" }
                )
            ) { entry ->
                val itemId = entry.arguments?.getString("itemId")?.takeIf { it.isNotBlank() }
                val type = entry.arguments?.getString("type") ?: "login"
                VaultEditScreen(
                    repository = repository,
                    itemId = itemId,
                    defaultType = type,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.AUDIT) {
                com.rklab.healthvault.ui.screens.audit.AuditLogScreen(
                    repository = repository,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.SHARES) {
                com.rklab.healthvault.ui.screens.documents.ShareHistoryScreen(
                    repository = repository,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.HOME) {
                val ctx = LocalContext.current
                LaunchedEffect(Unit) {
                    val app = ctx.applicationContext as com.rklab.healthvault.HealthVaultApp
                    if (app.pendingOpenCare) {
                        app.pendingOpenCare = false
                        navController.navigate(Routes.CARE)
                    }
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
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    isViewer = isViewer
                )
            }

            composable(Routes.SEARCH) {
                SearchScreen(
                    repository = repository,
                    onOpenDocument = { doc -> navController.navigate(Routes.viewer(doc.id, null)) }
                )
            }

            composable(Routes.CARE) {
                com.rklab.healthvault.ui.screens.care.CareScreen(repository = repository)
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

    pendingWebLogin?.let { challenge ->
        LoginChallengeDialog(
            repository = repository,
            challenge = challenge,
            onDone = { pendingWebLogin = null }
        )
    }
}

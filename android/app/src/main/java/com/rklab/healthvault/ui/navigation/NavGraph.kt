package com.rklab.healthvault.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.rklab.healthvault.ui.theme.HubBg
import com.rklab.healthvault.ui.theme.TextDark
import com.rklab.healthvault.ui.theme.VaultGold
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
import com.rklab.healthvault.ui.components.AiTab
import com.rklab.healthvault.ui.components.AiBottomNav
import com.rklab.healthvault.ui.screens.ai.AiAskScreen
import com.rklab.healthvault.ui.screens.ai.AiProvidersScreen
import com.rklab.healthvault.ui.screens.ai.AiUsageLogsScreen
import com.rklab.healthvault.ui.components.ExpenseTab
import com.rklab.healthvault.ui.components.ExpenseAnalyserBottomNav
import com.rklab.healthvault.ui.components.TrackerTab
import com.rklab.healthvault.ui.components.TrackerBottomNav
import com.rklab.healthvault.ui.screens.expense.ExpenseAnalyserInboxScreen
import com.rklab.healthvault.ui.screens.expense.ExpenseAnalyserInsightsScreen
import com.rklab.healthvault.ui.screens.expense.ExpenseAnalyserSettingsScreen
import com.rklab.healthvault.ui.screens.expense.ExpenseAnalyserSyncLogScreen
import com.rklab.healthvault.ui.screens.finance.*
import com.rklab.healthvault.ui.screens.locker.*
import com.rklab.healthvault.ui.screens.diary.*
import com.rklab.healthvault.ui.screens.tracker.ShopCatalogScreen
import com.rklab.healthvault.ui.screens.tracker.ShopDetailScreen
import com.rklab.healthvault.ui.screens.tracker.ShopFriendsScreen
import com.rklab.healthvault.ui.screens.tracker.ShopListScreen
import com.rklab.healthvault.ui.screens.tracker.ShopTrashScreen
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
import com.rklab.healthvault.util.VaultSendRequestNotifier
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
    const val FINANCE_TRANS = "finance_trans"
    const val FINANCE_STATS = "finance_stats"
    const val FINANCE_ACCOUNTS = "finance_accounts"
    const val FINANCE_MORE = "finance_more"
    const val FINANCE_ADD = "finance_add?accountId={accountId}&txnId={txnId}"
    const val FINANCE_ACCOUNT = "finance_account/{accountId}"
    const val FINANCE_INBOX = "finance_inbox"
    const val FINANCE_EMI = "finance_emi"
    const val LOCKER = "locker"
    const val LOCKER_EXPIRING = "locker_expiring"
    const val LOCKER_ADD = "locker_add?type={type}&scan={scan}"
    const val LOCKER_ITEM = "locker_item/{itemId}"
    const val DIARY = "diary"
    const val DIARY_PINNED = "diary_pinned"
    const val DIARY_ADD = "diary_add"
    const val DIARY_ENTRY = "diary_entry/{entryId}"
    const val URLS = "urls"
    const val URLS_FAVORITES = "urls_favorites"
    const val URLS_MANAGE = "urls_manage"
    const val URLS_ADD = "urls_add?categoryId={categoryId}"
    const val URLS_ITEM = "urls_item/{itemId}"
    const val AI = "ai"
    const val AI_PROVIDERS = "ai_providers"
    const val AI_LOGS = "ai_logs"
    const val EXPENSE = "expense"
    const val EXPENSE_INSIGHTS = "expense_insights"
    const val EXPENSE_LOG = "expense_log"
    const val EXPENSE_SETTINGS = "expense_settings"
    const val TRACKER = "tracker"
    const val TRACKER_FRIENDS = "tracker_friends"
    const val TRACKER_CATALOG = "tracker_catalog"
    const val TRACKER_TRASH = "tracker_trash"
    const val TRACKER_LIST = "tracker_list/{listId}"

    fun lockerAdd(type: String? = null, scan: Boolean = false) =
        "locker_add?type=${type ?: ""}&scan=${if (scan) "1" else "0"}"
    fun lockerItem(itemId: String) = "locker_item/$itemId"
    fun diaryEntry(entryId: String) = "diary_entry/$entryId"
    fun urlsAdd(categoryId: String? = null) = "urls_add?categoryId=${categoryId ?: ""}"
    fun urlsItem(itemId: String) = "urls_item/$itemId"
    fun trackerList(listId: String) = "tracker_list/$listId"

    fun financeAdd(accountId: String? = null, txnId: String? = null) =
        "finance_add?accountId=${accountId ?: ""}&txnId=${txnId ?: ""}"
    fun financeAccount(accountId: String) = "finance_account/$accountId"

    fun vaultSends(itemId: String? = null) = "vault_sends?itemId=${itemId ?: ""}"
    fun vaultItem(itemId: String) = "vault_item/$itemId"
    fun vaultEdit(itemId: String? = null, type: String = "login") =
        "vault_edit?itemId=${itemId ?: ""}&type=$type"
    const val SEARCH = "search"
    const val DOCTORS = "doctors"
    const val REMINDERS = "reminders"
    const val CARE = "care"
    const val FAMILY = "family"
    const val SETTINGS = "settings"
    const val QR_SCAN = "qr_scan"
    const val AUDIT = "audit"
    const val SHARES = "shares"
    const val CARDS = "cards/{personId}/{personName}"
    const val DOCUMENTS = "documents/{personId}?category={category}&custom_category={custom_category}&label={label}&hospital={hospital}"
    const val UPLOAD = "upload/{personId}?category={category}&camera={camera}&hospital={hospital}"
    const val VIEWER = "viewer/{docId}?fileId={fileId}"
    const val EDIT = "edit/{docId}"

    fun cards(personId: String, personName: String) = "cards/$personId/$personName"
    fun documents(
        personId: String,
        category: DocCategory?,
        customCategory: String?,
        hospital: String? = null
    ): String {
        val label = customCategory ?: category?.name ?: "Documents"
        val hosp = android.net.Uri.encode(hospital.orEmpty())
        return "documents/$personId?category=${category?.name ?: ""}&custom_category=${customCategory ?: ""}&label=$label&hospital=$hosp"
    }
    fun upload(
        personId: String,
        category: DocCategory?,
        camera: Boolean = false,
        hospital: String? = null
    ): String {
        val hosp = android.net.Uri.encode(hospital.orEmpty())
        return "upload/$personId?category=${category?.name ?: ""}&camera=${if (camera) "1" else "0"}&hospital=$hosp"
    }
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
    var pendingSendRequest by remember { mutableStateOf<com.rklab.healthvault.data.model.VaultSendRequestOut?>(null) }
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(repository.isLoggedIn, start, lifecycleOwner) {
        if (!repository.isLoggedIn || start == Routes.LOGIN || start == Routes.SERVER_SETUP) {
            pendingWebLogin = null
            pendingSendRequest = null
            return@LaunchedEffect
        }
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            val app = context.applicationContext as com.rklab.healthvault.HealthVaultApp
            if (app.pendingOpenVaultSends) {
                app.pendingOpenVaultSends = false
                navController.navigate(Routes.VAULT) {
                    popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                    launchSingleTop = true
                }
                navController.navigate(Routes.vaultSends())
            }
            while (true) {
                runCatching {
                    val next = repository.pendingLoginChallenges().firstOrNull()
                    pendingWebLogin = next
                    if (next != null) LoginChallengeNotifier.show(context, next)
                }
                runCatching {
                    val pending = repository.listVaultSendRequests("pending")
                    pending.take(3).forEach { VaultSendRequestNotifier.show(context, it) }
                    if (pendingSendRequest == null) {
                        pendingSendRequest = pending.firstOrNull()
                    } else if (pending.none { it.id == pendingSendRequest?.id }) {
                        pendingSendRequest = pending.firstOrNull()
                    }
                }
                if (app.pendingOpenVaultSends) {
                    app.pendingOpenVaultSends = false
                    navController.navigate(Routes.VAULT) {
                        popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                        launchSingleTop = true
                    }
                    navController.navigate(Routes.vaultSends())
                }
                delay(2_000)
            }
        }
    }

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route

    val mainTabs = setOf(Routes.HOME, Routes.DOCTORS, Routes.CARE, Routes.REMINDERS, Routes.FAMILY)
    val passwordTabs = setOf(Routes.VAULT, Routes.VAULT_GENERATOR, Routes.VAULT_HEALTH, "vault_sends?itemId={itemId}")
    val financeTabs = setOf(Routes.FINANCE, Routes.FINANCE_TRANS, Routes.FINANCE_STATS, Routes.FINANCE_ACCOUNTS, Routes.FINANCE_MORE)
    val lockerTabs = setOf(Routes.LOCKER, Routes.LOCKER_EXPIRING)
    val diaryTabs = setOf(Routes.DIARY, Routes.DIARY_PINNED)
    val urlTabs = setOf(Routes.URLS, Routes.URLS_FAVORITES, Routes.URLS_MANAGE)
    val aiTabs = setOf(Routes.AI, Routes.AI_PROVIDERS, Routes.AI_LOGS)
    val expenseTabs = setOf(Routes.EXPENSE, Routes.EXPENSE_INSIGHTS, Routes.EXPENSE_LOG, Routes.EXPENSE_SETTINGS)
    val trackerTabs = setOf(Routes.TRACKER, Routes.TRACKER_FRIENDS, Routes.TRACKER_CATALOG, Routes.TRACKER_TRASH)
    val onFinanceAccount = currentRoute?.startsWith("finance_account/") == true
    val onLockerItem = currentRoute?.startsWith("locker_item/") == true
    val onLockerAdd = currentRoute?.startsWith("locker_add") == true
    val onUrlItem = currentRoute?.startsWith("urls_item/") == true
    val onUrlAdd = currentRoute?.startsWith("urls_add") == true
    val onTrackerList = currentRoute?.startsWith("tracker_list/") == true

    val hideAskAiFab = !repository.isLoggedIn
        || currentRoute in aiTabs
        || currentRoute == Routes.LOGIN
        || currentRoute == Routes.SERVER_SETUP
        || currentRoute == Routes.QR_SCAN
    val showAskAiFab by repository.tokenManager.isShowAskAiFab.collectAsState(initial = true)

    Scaffold(
        containerColor = HubBg,
        floatingActionButton = {
            if (!hideAskAiFab && showAskAiFab) {
                FloatingActionButton(
                    onClick = {
                        navController.navigate(Routes.AI) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    modifier = Modifier.padding(bottom = 72.dp),
                    containerColor = VaultGold,
                    contentColor = TextDark,
                ) {
                    Icon(Icons.Filled.SmartToy, contentDescription = "Ask AI")
                }
            }
        },
        bottomBar = {
            if (currentRoute in trackerTabs || onTrackerList) {
                val current = when (currentRoute) {
                    Routes.TRACKER_FRIENDS -> TrackerTab.FRIENDS
                    Routes.TRACKER_CATALOG -> TrackerTab.CATALOG
                    Routes.TRACKER_TRASH -> TrackerTab.TRASH
                    else -> TrackerTab.LISTS
                }
                TrackerBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        TrackerTab.FRIENDS -> Routes.TRACKER_FRIENDS
                        TrackerTab.CATALOG -> Routes.TRACKER_CATALOG
                        TrackerTab.TRASH -> Routes.TRACKER_TRASH
                        TrackerTab.LISTS -> Routes.TRACKER
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.TRACKER) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in lockerTabs || onLockerItem || onLockerAdd) {
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
                    currentRoute == Routes.FINANCE_TRANS -> FinanceTab.TRANS
                    currentRoute == Routes.FINANCE_STATS -> FinanceTab.STATS
                    currentRoute == Routes.FINANCE_ACCOUNTS || onFinanceAccount -> FinanceTab.ACCOUNTS
                    currentRoute == Routes.FINANCE_MORE -> FinanceTab.MORE
                    else -> FinanceTab.HOME
                }
                FinanceBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        FinanceTab.HOME -> Routes.FINANCE
                        FinanceTab.TRANS -> Routes.FINANCE_TRANS
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
            } else if (currentRoute in expenseTabs) {
                val current = when (currentRoute) {
                    Routes.EXPENSE_INSIGHTS -> ExpenseTab.INSIGHTS
                    Routes.EXPENSE_LOG -> ExpenseTab.LOG
                    Routes.EXPENSE_SETTINGS -> ExpenseTab.SETTINGS
                    else -> ExpenseTab.INBOX
                }
                ExpenseAnalyserBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        ExpenseTab.INBOX -> Routes.EXPENSE
                        ExpenseTab.INSIGHTS -> Routes.EXPENSE_INSIGHTS
                        ExpenseTab.LOG -> Routes.EXPENSE_LOG
                        ExpenseTab.SETTINGS -> Routes.EXPENSE_SETTINGS
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.EXPENSE) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in aiTabs) {
                val current = when (currentRoute) {
                    Routes.AI_PROVIDERS -> AiTab.PROVIDERS
                    Routes.AI_LOGS -> AiTab.LOGS
                    else -> AiTab.ASK
                }
                AiBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        AiTab.ASK -> Routes.AI
                        AiTab.PROVIDERS -> Routes.AI_PROVIDERS
                        AiTab.LOGS -> Routes.AI_LOGS
                    }
                    navController.navigate(route) {
                        popUpTo(Routes.AI) { inclusive = false; saveState = true }
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
                    // Pop to the module hub so switching tabs always lands on a fresh
                    // destination (popUpTo(VAULT) was a no-op from Send when Vault was
                    // already under the stack, so the Vault tab appeared dead).
                    navController.navigate(route) {
                        popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            } else if (currentRoute in mainTabs) {
                val current = when (currentRoute) {
                    Routes.DOCTORS -> MainTab.DOCTORS
                    Routes.CARE -> MainTab.CARE
                    Routes.REMINDERS -> MainTab.REMINDERS
                    Routes.FAMILY -> MainTab.FAMILY
                    else -> MainTab.HOME
                }
                HealthVaultBottomNav(current = current) { tab ->
                    val route = when (tab) {
                        MainTab.HOME -> Routes.HOME
                        MainTab.DOCTORS -> Routes.DOCTORS
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
                    onExpense = {
                        navController.navigate(Routes.EXPENSE) {
                            popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                            launchSingleTop = true
                        }
                    },
                    onAi = {
                        navController.navigate(Routes.AI) {
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
                    onTracker = {
                        navController.navigate(Routes.TRACKER) {
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
                    onDiary = {
                        navController.navigate(Routes.DIARY) {
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

            composable(Routes.TRACKER) {
                ShopListScreen(
                    repository = repository,
                    onOpenList = { navController.navigate(Routes.trackerList(it)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.TRACKER_FRIENDS) {
                ShopFriendsScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    onOpenList = { navController.navigate(Routes.trackerList(it)) }
                )
            }
            composable(Routes.TRACKER_CATALOG) {
                ShopCatalogScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.TRACKER_TRASH) {
                ShopTrashScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(
                Routes.TRACKER_LIST,
                arguments = listOf(navArgument("listId") { type = NavType.StringType })
            ) { entry ->
                val listId = entry.arguments?.getString("listId") ?: return@composable
                ShopDetailScreen(
                    repository = repository,
                    listId = listId,
                    onBack = { navController.popBackStack() }
                )
            }

            composable(Routes.LOCKER) {
                LockerListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.lockerItem(it)) },
                    onAdd = { navController.navigate(Routes.lockerAdd(it)) },
                    onScan = { navController.navigate(Routes.lockerAdd(it, scan = true)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.LOCKER_EXPIRING) {
                LockerListScreen(
                    repository = repository,
                    onOpenItem = { navController.navigate(Routes.lockerItem(it)) },
                    onAdd = { navController.navigate(Routes.lockerAdd(it)) },
                    onScan = { navController.navigate(Routes.lockerAdd(it, scan = true)) },
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    expiringOnly = true
                )
            }
            composable(
                Routes.LOCKER_ADD,
                arguments = listOf(
                    navArgument("type") { type = NavType.StringType; defaultValue = "" },
                    navArgument("scan") { type = NavType.StringType; defaultValue = "0" }
                )
            ) { entry ->
                val type = entry.arguments?.getString("type").orEmpty().ifBlank { null }
                val startScan = entry.arguments?.getString("scan") == "1"
                LockerAddScreen(
                    repository = repository,
                    defaultType = type,
                    startWithScanner = startScan,
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
            composable(Routes.DIARY) {
                DiaryListScreen(
                    repository = repository,
                    onOpenEntry = { navController.navigate(Routes.diaryEntry(it)) },
                    onAdd = { navController.navigate(Routes.DIARY_ADD) },
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.DIARY_PINNED) {
                DiaryListScreen(
                    repository = repository,
                    onOpenEntry = { navController.navigate(Routes.diaryEntry(it)) },
                    onAdd = { navController.navigate(Routes.DIARY_ADD) },
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    pinnedOnly = true
                )
            }
            composable(Routes.DIARY_ADD) {
                DiaryAddScreen(
                    repository = repository,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() }
                )
            }
            composable(
                Routes.DIARY_ENTRY,
                arguments = listOf(navArgument("entryId") { type = NavType.StringType })
            ) { entry ->
                DiaryEntryScreen(
                    repository = repository,
                    entryId = entry.arguments?.getString("entryId").orEmpty(),
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

            composable(Routes.AI) {
                AiAskScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.AI_PROVIDERS) {
                AiProvidersScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.AI_LOGS) {
                AiUsageLogsScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }

            composable(Routes.EXPENSE) {
                ExpenseAnalyserInboxScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.EXPENSE_INSIGHTS) {
                ExpenseAnalyserInsightsScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.EXPENSE_LOG) {
                ExpenseAnalyserSyncLogScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }
            composable(Routes.EXPENSE_SETTINGS) {
                ExpenseAnalyserSettingsScreen(
                    repository = repository,
                    onOpenModules = { navController.navigate(Routes.MODULES) }
                )
            }

            composable(Routes.FINANCE) {
                FinanceHomeScreen(
                    repository = repository,
                    onAdd = { navController.navigate(Routes.financeAdd()) },
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    onSeeAll = { navController.navigate(Routes.FINANCE_TRANS) },
                    onEdit = { id -> navController.navigate(Routes.financeAdd(txnId = id)) }
                )
            }
            composable(Routes.FINANCE_TRANS) {
                FinanceTransScreen(
                    repository = repository,
                    onAdd = { navController.navigate(Routes.financeAdd()) },
                    onOpenModules = { navController.navigate(Routes.MODULES) },
                    onEdit = { id -> navController.navigate(Routes.financeAdd(txnId = id)) }
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
                    onOpenEmi = { navController.navigate(Routes.FINANCE_EMI) },
                    onOpenAiProviders = { navController.navigate(Routes.AI_PROVIDERS) },
                    onOpenExpense = { navController.navigate(Routes.EXPENSE) }
                )
            }
            composable(Routes.FINANCE_EMI) {
                FinanceEmiScreen(repository) { navController.popBackStack() }
            }
            composable(
                Routes.FINANCE_ADD,
                arguments = listOf(
                    navArgument("accountId") { type = NavType.StringType; nullable = true; defaultValue = "" },
                    navArgument("txnId") { type = NavType.StringType; nullable = true; defaultValue = "" }
                )
            ) { entry ->
                val prefill = entry.arguments?.getString("accountId")?.takeIf { it.isNotBlank() }
                val txnId = entry.arguments?.getString("txnId")?.takeIf { it.isNotBlank() }
                FinanceAddScreen(
                    repository = repository,
                    onDone = { navController.popBackStack() },
                    onBack = { navController.popBackStack() },
                    prefillAccountId = prefill,
                    txnId = txnId
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
                    onOpenFolder = { personId, category, customCategory, hospital ->
                        navController.navigate(Routes.documents(personId, category, customCategory, hospital))
                    },
                    onAddDocument = { personId, hospital ->
                        navController.navigate(Routes.upload(personId, null, hospital = hospital))
                    },
                    onOpenDocument = { doc, fileId ->
                        navController.navigate(Routes.viewer(doc.id, fileId))
                    },
                    onAddCard = { personId, personName ->
                        navController.navigate(Routes.cards(personId, personName))
                    },
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

            composable(Routes.DOCTORS) {
                com.rklab.healthvault.ui.screens.doctors.DoctorsScreen(repository = repository)
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
                    navArgument("label") { type = NavType.StringType; defaultValue = "" },
                    navArgument("hospital") { type = NavType.StringType; nullable = true; defaultValue = "" }
                )
            ) { entry ->
                val personId = entry.arguments?.getString("personId").orEmpty()
                val categoryStr = entry.arguments?.getString("category").orEmpty()
                val category = categoryStr.takeIf { it.isNotBlank() }?.let { DocCategory.valueOf(it) }
                val customCategory = entry.arguments?.getString("custom_category")?.takeIf { it.isNotBlank() }
                val hospital = entry.arguments?.getString("hospital")?.takeIf { it.isNotBlank() }
                val label = buildString {
                    append(entry.arguments?.getString("label") ?: "Documents")
                    if (!hospital.isNullOrBlank()) append(" · $hospital")
                }

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
                        hospital = hospital,
                        title = label,
                        onBack = { navController.popBackStack() },
                        onAddDocument = {
                            navController.navigate(
                                Routes.upload(resolvedPersonId, category, hospital = hospital)
                            )
                        },
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
                    navArgument("camera") { type = NavType.StringType; nullable = true; defaultValue = "0" },
                    navArgument("hospital") { type = NavType.StringType; nullable = true; defaultValue = "" }
                )
            ) { entry ->
                val personId = entry.arguments?.getString("personId").orEmpty()
                val categoryStr = entry.arguments?.getString("category").orEmpty()
                val category = categoryStr.takeIf { it.isNotBlank() }?.let { DocCategory.valueOf(it) }
                val autoCamera = entry.arguments?.getString("camera") == "1"
                val defaultHospital = entry.arguments?.getString("hospital")?.takeIf { it.isNotBlank() }

                var resolvedPersonId by remember { mutableStateOf(personId) }
                LaunchedEffect(Unit) {
                    if (resolvedPersonId.isBlank()) {
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
                        defaultHospital = defaultHospital,
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
    pendingSendRequest?.takeIf { pendingWebLogin == null }?.let { req ->
        com.rklab.healthvault.ui.screens.passwords.VaultSendRequestDialog(
            repository = repository,
            request = req,
            onOpenSend = {
                navController.navigate(Routes.VAULT) {
                    popUpTo(Routes.MODULES) { inclusive = false; saveState = true }
                    launchSingleTop = true
                }
                navController.navigate(Routes.vaultSends())
            },
            onDone = { pendingSendRequest = null }
        )
    }
}

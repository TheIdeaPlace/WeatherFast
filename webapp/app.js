/**
 * FastWeather Web Application
 * Accessible weather application with WCAG 2.2 AA compliance
 * Version: 2.1.1 - Location detection fixed
 */

// Constants
const KMH_TO_MPH = 0.621371;
const MM_TO_INCHES = 0.0393701;
const HPA_TO_INHG = 0.02953;
const M_TO_MILES = 0.000621371;
const M_TO_KM = 0.001;
const OPEN_METEO_API_URL = 'https://api.open-meteo.com/v1/forecast';
const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';

// WMO Weather interpretation codes
const WEATHER_CODES = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Depositing rime fog',
    51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
    56: 'Light freezing drizzle', 57: 'Dense freezing drizzle',
    61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
    66: 'Light freezing rain', 67: 'Heavy freezing rain',
    71: 'Slight snow fall', 73: 'Moderate snow fall', 75: 'Heavy snow fall',
    77: 'Snow grains',
    80: 'Slight rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers',
    85: 'Slight snow showers', 86: 'Heavy snow showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with slight hail', 99: 'Thunderstorm with heavy hail'
};

// Default configuration - intelligent defaults for best user experience
const DEFAULT_CONFIG = {
    current: {
        temperature: true,
        feels_like: true,
        humidity: true,
        wind_speed: true,
        wind_direction: false,
        wind_gusts: false,
        pressure: false,
        visibility: false,
        uv_index: false,
        dew_point: false,
        precipitation: true,
        cloud_cover: false,
        rain: false,
        showers: false,
        snowfall: false
    },
    hourly: {
        temperature: true,
        feels_like: false,
        humidity: false,
        precipitation: true,
        precipitation_probability: true,
        uv_index: false,
        wind_speed: false,
        wind_gusts: false,
        dew_point: false,
        cloud_cover: false
    },
    daily: {
        temperature_max: true,
        temperature_min: true,
        sunrise: true,
        sunset: true,
        precipitation_sum: true,
        precipitation_probability: true,
        uv_index_max: false,
        daylight_duration: false,
        sunshine_duration: false,
        wind_speed_max: false
    },
    cityList: {
        temperature: true,
        conditions: true,
        feels_like: false,
        humidity: false,
        wind_speed: false,
        wind_direction: false,
        wind_gusts: false,
        uv_index: false,
        high_temp: true,
        low_temp: true,
        sunrise: false,
        sunset: false
    },
    cityListOrder: ['temperature', 'conditions', 'high_temp', 'low_temp', 'feels_like', 'humidity', 'wind_speed', 'wind_gusts', 'wind_direction', 'uv_index', 'sunrise', 'sunset'],
    units: {
        temperature: 'F',
        wind_speed: 'mph',
        precipitation: 'in',
        pressure: 'inHg',
        distance: 'mi'
    },
    defaultView: 'flat',
    listViewStyle: 'detailed',
    currentConditionsView: 'flat',
    hourlyDetailView: 'flat',
    dailyDetailView: 'flat'
};

// Application state
let cities = {};
let weatherData = {};
let currentConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
let currentCityMatches = [];
let focusReturnElement = null;
let currentView = 'flat'; // 'flat', 'table', or 'list'
let listNavigationHandler = null;
let cachedCityCoordinates = null; // Cache for pre-geocoded US city coordinates
let cachedInternationalCoordinates = null; // Cache for pre-geocoded international city coordinates
let cachedPlaceCategories = []; // Places of the World lists (see places.js)
let nwsPlaceNames = new Set();  // saved names of Places of the World places NWS covers
let placesReady = Promise.resolve(); // settles once Places of the World has loaded (or failed)
let currentStateCities = null; // Store current state cities being viewed
let currentStateName = null; // Store current state name
let currentLocationType = 'us'; // 'us' or 'international'

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    console.log('=== FastWeather Initializing ===');
    loadCitiesFromStorage();
    console.log('After loadCitiesFromStorage, cities:', Object.keys(cities));
    loadConfigFromStorage();
    
    // Set initial view from config
    if (currentConfig.defaultView) {
        currentView = currentConfig.defaultView;
    }
    
    // Update view button label and menu checkmarks to match initial view
    const viewLabel = currentView.charAt(0).toUpperCase() + currentView.slice(1);
    document.getElementById('current-view-label').textContent = `View: ${viewLabel}`;
    document.querySelectorAll('#view-menu [role="menuitem"]').forEach(item => {
        const isSelected = item.dataset.view === currentView;
        item.setAttribute('aria-checked', isSelected ? 'true' : 'false');
    });
    
    initializeEventListeners();
    // Started before the list renders: the list's alert checks wait for it
    // to know which saved places are in the US
    placesReady = loadPlacesOfTheWorld();
    console.log('About to renderCityList, cities count:', Object.keys(cities).length);
    renderCityList();
    
    // Load cached city coordinates
    console.log('About to load cached city coordinates...');
    await loadCachedCityCoordinates();
    console.log('After loadCachedCityCoordinates, cachedCityCoordinates is:', cachedCityCoordinates ? 'LOADED' : 'NULL/UNDEFINED');
    
    // Load cached international city coordinates
    console.log('About to load cached international city coordinates...');
    await loadCachedInternationalCoordinates();
    console.log('After loadCachedInternationalCoordinates, cachedInternationalCoordinates is:', cachedInternationalCoordinates ? 'LOADED' : 'NULL/UNDEFINED');

    await placesReady;

    announceToScreenReader('FastWeather application loaded');
    console.log('=== FastWeather Initialization Complete ===');
});

// Load cached city coordinates from JSON file
async function loadCachedCityCoordinates() {
    try {
        console.log('Fetching us-cities-cached.json...');
        const response = await fetch('us-cities-cached.json');
        console.log('Fetch response:', response.status, response.statusText);
        if (response.ok) {
            cachedCityCoordinates = await response.json();
            const stateCount = cachedCityCoordinates ? Object.keys(cachedCityCoordinates).length : 0;
            const states = cachedCityCoordinates ? Object.keys(cachedCityCoordinates).join(', ') : 'none';
            console.log(`✓ Successfully loaded cached city coordinates for ${stateCount} states: ${states}`);
            
            // Add a global debug function for easy access
            window.debugCache = () => {
                console.log('=== Cache Debug Info ===');
                console.log('cachedCityCoordinates exists:', !!cachedCityCoordinates);
                if (cachedCityCoordinates) {
                    console.log('States in cache:', Object.keys(cachedCityCoordinates));
                    Object.keys(cachedCityCoordinates).forEach(state => {
                        console.log(`  ${state}: ${cachedCityCoordinates[state].length} cities`);
                    });
                }
            };
            console.log('You can run debugCache() in console to check cache status');
            console.log('You can run reloadCache() to try loading again');
        } else {
            console.error(`❌ Failed to fetch cached city coordinates: HTTP ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        console.error('❌ Could not load cached city coordinates:', error);
        console.error('Error details:', error.message, error.stack);
    }
}

// Load international cached city coordinates
async function loadCachedInternationalCoordinates() {
    try {
        console.log('Fetching international-cities-cached.json...');
        const response = await fetch('international-cities-cached.json');
        console.log('Fetch response:', response.status, response.statusText);
        if (response.ok) {
            cachedInternationalCoordinates = await response.json();
            const countryCount = cachedInternationalCoordinates ? Object.keys(cachedInternationalCoordinates).length : 0;
            const countries = cachedInternationalCoordinates ? Object.keys(cachedInternationalCoordinates).join(', ') : 'none';
            console.log(`✓ Successfully loaded cached international city coordinates for ${countryCount} countries`);
            
            // Populate the country dropdown
            populateCountryDropdown();
        } else {
            console.error(`❌ Failed to fetch cached international city coordinates: HTTP ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        console.error('❌ Could not load cached international city coordinates:', error);
        console.error('Error details:', error.message, error.stack);
    }
}

// Load Places of the World and fill its list chooser. Without the file the
// tab says so rather than offering an empty list.
async function loadPlacesOfTheWorld() {
    try {
        const response = await fetch('places-of-the-world.json');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        cachedPlaceCategories = parsePlaceCategories(await response.json());
    } catch (error) {
        console.error('Could not load places-of-the-world.json:', error);
        cachedPlaceCategories = [];
    }
    nwsPlaceNames = nwsPlaceSavedNames(cachedPlaceCategories);
    populatePlacesDropdown();
}

function populatePlacesDropdown() {
    const select = document.getElementById('places-select');
    const description = document.getElementById('places-description');
    if (!select) return;
    while (select.options.length > 1) {
        select.remove(1);
    }
    cachedPlaceCategories.forEach(category => {
        const option = document.createElement('option');
        option.value = category.name;
        option.textContent = placeCategoryLabel(category);
        select.appendChild(option);
    });
    if (description && cachedPlaceCategories.length === 0) {
        description.textContent = 'Places of the World could not be loaded. Please refresh the page.';
    }
}

// The chosen list's description, read with the list chooser (aria-describedby)
function updatePlacesDescription() {
    const select = document.getElementById('places-select');
    const description = document.getElementById('places-description');
    if (!select || !description) return;
    const category = cachedPlaceCategories.find(c => c.name === select.value);
    description.textContent = (category && category.description) || PLACES_DEFAULT_DESCRIPTION;
}

const PLACES_DEFAULT_DESCRIPTION = 'Famous bridges, beaches and extreme weather places, each with its weather.';

// Populate country dropdown from cached data
function populateCountryDropdown() {
    if (!cachedInternationalCoordinates) {
        console.error('Cannot populate country dropdown: cachedInternationalCoordinates is not loaded');
        return;
    }
    
    // Get sorted list of countries
    const countries = Object.keys(cachedInternationalCoordinates).sort();
    
    // Country name to ISO code mapping (needed for Add City filter)
    const countryCodeMap = {
        'Algeria': 'dz', 'Angola': 'ao', 'Argentina': 'ar', 'Armenia': 'am', 'Australia': 'au',
        'Austria': 'at', 'Azerbaijan': 'az', 'Bahrain': 'bh', 'Bangladesh': 'bd', 'Belgium': 'be',
        'Bolivia': 'bo', 'Brazil': 'br', 'Bulgaria': 'bg', 'Cambodia': 'kh', 'Cameroon': 'cm',
        'Canada': 'ca', 'Chile': 'cl', 'China': 'cn', 'Colombia': 'co', 'Costa Rica': 'cr',
        'Croatia': 'hr', "Côte d'Ivoire": 'ci', 'Cuba': 'cu', 'Czech Republic': 'cz', 'Denmark': 'dk',
        'Dominican Republic': 'do', 'Ecuador': 'ec', 'Egypt': 'eg', 'El Salvador': 'sv', 'Ethiopia': 'et',
        'Finland': 'fi', 'France': 'fr', 'Georgia': 'ge', 'Germany': 'de', 'Ghana': 'gh',
        'Greece': 'gr', 'Greenland': 'gl', 'Guatemala': 'gt', 'Honduras': 'hn', 'Hungary': 'hu',
        'India': 'in', 'Indonesia': 'id', 'Iran': 'ir', 'Iraq': 'iq', 'Ireland': 'ie',
        'Israel': 'il', 'Italy': 'it', 'Jamaica': 'jm', 'Japan': 'jp', 'Jordan': 'jo',
        'Kazakhstan': 'kz', 'Kenya': 'ke', 'Kuwait': 'kw', 'Laos': 'la', 'Lebanon': 'lb',
        'Malaysia': 'my', 'Mexico': 'mx', 'Morocco': 'ma', 'Mozambique': 'mz', 'Myanmar': 'mm',
        'Netherlands': 'nl', 'New Zealand': 'nz', 'Nigeria': 'ng', 'Norway': 'no', 'Oman': 'om',
        'Pakistan': 'pk', 'Panama': 'pa', 'Paraguay': 'py', 'Peru': 'pe', 'Philippines': 'ph',
        'Poland': 'pl', 'Portugal': 'pt', 'Qatar': 'qa', 'Romania': 'ro', 'Russia': 'ru',
        'Saudi Arabia': 'sa', 'Senegal': 'sn', 'Serbia': 'rs', 'Singapore': 'sg', 'Slovakia': 'sk',
        'Slovenia': 'si', 'South Africa': 'za', 'South Korea': 'kr', 'Spain': 'es', 'Sweden': 'se',
        'Switzerland': 'ch', 'Taiwan': 'tw', 'Tanzania': 'tz', 'Thailand': 'th', 'Trinidad and Tobago': 'tt',
        'Tunisia': 'tn', 'Turkey': 'tr', 'Uganda': 'ug', 'Ukraine': 'ua', 'United Arab Emirates': 'ae',
        'United Kingdom': 'gb', 'United States': 'us', 'Uruguay': 'uy', 'Uzbekistan': 'uz',
        'Venezuela': 've', 'Vietnam': 'vn', 'Zimbabwe': 'zw'
    };
    
    // 1. Populate Browse Cities dropdown (country-select-browse) - uses country names
    const browseSelect = document.getElementById('country-select-browse');
    if (browseSelect) {
        while (browseSelect.options.length > 1) {
            browseSelect.remove(1);
        }
        countries.forEach(country => {
            const option = document.createElement('option');
            option.value = country;
            option.textContent = country;
            browseSelect.appendChild(option);
        });
        console.log(`✓ Populated Browse Cities dropdown with ${countries.length} countries`);
    }
    
    // 2. Populate Add City filter dropdown (country-select) - uses ISO codes
    const filterSelect = document.getElementById('country-select');
    if (filterSelect) {
        while (filterSelect.options.length > 1) {
            filterSelect.remove(1);
        }
        countries.forEach(country => {
            const option = document.createElement('option');
            const code = countryCodeMap[country] || country.toLowerCase().substring(0, 2);
            option.value = code;
            option.textContent = country;
            filterSelect.appendChild(option);
        });
        console.log(`✓ Populated Add City filter dropdown with ${countries.length} countries`);
    }
}

// Browse tabs: type -> [tab id, panel id]
const LOCATION_TABS = {
    us: ['us-states-tab', 'us-states-panel'],
    international: ['international-tab', 'international-panel'],
    places: ['places-tab', 'places-panel']
};

// Switch between the U.S. States, International and Places of the World tabs
function switchLocationTab(type) {
    if (!LOCATION_TABS[type]) return;
    currentLocationType = type;

    Object.entries(LOCATION_TABS).forEach(([key, [tabId, panelId]]) => {
        const tab = document.getElementById(tabId);
        const panel = document.getElementById(panelId);
        const selected = key === type;
        if (tab) {
            tab.setAttribute('aria-selected', selected ? 'true' : 'false');
            tab.setAttribute('tabindex', selected ? '0' : '-1');
        }
        if (panel) panel.hidden = !selected;
    });

    // Clear error messages when switching tabs
    const errorDiv = document.getElementById('state-selector-error');
    clearError(errorDiv);
}

// Manual cache reload function for debugging
window.reloadCache = async function() {
    console.log('Manually reloading caches...');
    await loadCachedCityCoordinates();
    await loadCachedInternationalCoordinates();
    if (cachedCityCoordinates) {
        console.log('✓ US cache reloaded successfully');
        window.debugCache();
    }
    if (cachedInternationalCoordinates) {
        console.log('✓ International cache reloaded successfully');
    }
};

// Event Listeners
function initializeEventListeners() {
    // Add city form
    document.getElementById('add-city-form').addEventListener('submit', handleAddCity);
    
    // Location detection button
    document.getElementById('location-btn').addEventListener('click', detectLocation);
    
    // Location tabs (U.S. States / International)
    document.getElementById('us-states-tab').addEventListener('click', () => switchLocationTab('us'));
    document.getElementById('international-tab').addEventListener('click', () => switchLocationTab('international'));
    document.getElementById('places-tab').addEventListener('click', () => switchLocationTab('places'));
    document.getElementById('places-select').addEventListener('change', updatePlacesDescription);

    // State selector form
    document.getElementById('state-selector-form').addEventListener('submit', handleStateSelection);
    
    // Configuration dialog
    document.getElementById('configure-btn').addEventListener('click', openConfigDialog);
    document.getElementById('apply-config-btn').addEventListener('click', applyConfiguration);
    document.getElementById('save-config-btn').addEventListener('click', saveConfiguration);
    document.getElementById('cancel-config-btn').addEventListener('click', closeConfigDialog);
    
    // Reset buttons
    document.getElementById('reset-cities-btn').addEventListener('click', resetCities);
    document.getElementById('reset-settings-btn').addEventListener('click', resetSettings);
    document.getElementById('reset-all-btn').addEventListener('click', resetAll);
    
    // Check All / Uncheck All buttons
    document.querySelectorAll('.check-all-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const target = e.target.dataset.target;
            document.querySelectorAll(`input[name^="${target}-"]`).forEach(checkbox => {
                checkbox.checked = true;
            });
        });
    });
    
    document.querySelectorAll('.uncheck-all-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const target = e.target.dataset.target;
            document.querySelectorAll(`input[name^="${target}-"]`).forEach(checkbox => {
                checkbox.checked = false;
            });
        });
    });
    
    // Debug panel buttons
    document.getElementById('debug-check-status-btn').addEventListener('click', checkDebugStatus);
    document.getElementById('debug-clear-cache-btn').addEventListener('click', clearDebugCaches);
    document.getElementById('debug-unregister-sw-btn').addEventListener('click', unregisterServiceWorker);
    
    // City selection dialog
    document.getElementById('select-city-btn').addEventListener('click', handleCitySelection);
    document.getElementById('cancel-selection-btn').addEventListener('click', closeCitySelectionDialog);
    
    // Refresh all
    document.getElementById('refresh-all-btn').addEventListener('click', refreshAllCities);
    
    // View menu button
    const viewMenuBtn = document.getElementById('view-menu-btn');
    const viewMenu = document.getElementById('view-menu');
    
    viewMenuBtn.addEventListener('click', toggleViewMenu);
    
    // Menu item clicks
    document.querySelectorAll('#view-menu [role="menuitem"]').forEach(item => {
        item.addEventListener('click', (e) => {
            const view = e.target.dataset.view;
            switchView(view);
            closeViewMenu();
        });
    });
    
    // Close menu on Escape or outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.view-menu-container')) {
            closeViewMenu();
        }
    });
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && viewMenu.hidden === false) {
            closeViewMenu();
            viewMenuBtn.focus();
        }
    });
    
    // Keyboard navigation in menu
    viewMenu.addEventListener('keydown', handleViewMenuKeydown);
    
    // Close weather details
    document.getElementById('close-weather-details-btn').addEventListener('click', closeWeatherDetailsDialog);
    
    // Tab navigation for config dialog
    setupTabNavigation();
    
    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);
    
    // Close modals on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllModals();
        }
    });
}

// Keyboard shortcuts
function handleKeyboardShortcuts(e) {
    // Ctrl+R: Refresh all cities
    if (e.ctrlKey && e.key === 'r') {
        e.preventDefault();
        refreshAllCities();
    }
    
    // Alt+V: Open view menu
    if (e.altKey && e.key === 'v') {
        e.preventDefault();
        const viewMenuBtn = document.getElementById('view-menu-btn');
        if (viewMenuBtn && !document.getElementById('config-dialog').hidden === false) {
            toggleViewMenu();
            announceToScreenReader('View menu opened');
        }
    }
    
    // Alt+G: Open configuration dialog
    if (e.altKey && e.key === 'g') {
        e.preventDefault();
        const configDialog = document.getElementById('config-dialog');
        if (configDialog && configDialog.hidden) {
            openConfigDialog();
            announceToScreenReader('Configuration dialog opened');
        }
    }
    
    // Alt+L: Use current location
    if (e.altKey && e.key === 'l') {
        e.preventDefault();
        const locationBtn = document.getElementById('location-btn');
        if (locationBtn && !locationBtn.disabled) {
            locationBtn.click();
            announceToScreenReader('Getting current location');
        }
    }
}

// Tab navigation, one tablist at a time: the Browse tabs and the Configure
// dialog's tabs are separate groups, so arrowing never leaves the group, and
// selecting a tab hides only its own group's panels.
function setupTabNavigation() {
    document.querySelectorAll('[role="tablist"]').forEach(tablist => {
        setupTabList(Array.from(tablist.querySelectorAll('[role="tab"]')));
    });
}

function setupTabList(tabs) {
    const panels = tabs
        .map(tab => document.getElementById(tab.getAttribute('aria-controls')))
        .filter(Boolean);

    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => activateTab(tab, tabs, panels));
        tab.addEventListener('keydown', (e) => {
            let newIndex = index;
            
            if (e.key === 'ArrowRight') {
                newIndex = (index + 1) % tabs.length;
                e.preventDefault();
            } else if (e.key === 'ArrowLeft') {
                newIndex = (index - 1 + tabs.length) % tabs.length;
                e.preventDefault();
            } else if (e.key === 'Home') {
                newIndex = 0;
                e.preventDefault();
            } else if (e.key === 'End') {
                newIndex = tabs.length - 1;
                e.preventDefault();
            }
            
            if (newIndex !== index) {
                // A click, so the tab's own handlers run too (the Browse tabs
                // track which kind of place the form loads).
                tabs[newIndex].click();
                tabs[newIndex].focus();
            }
        });
    });
}

function activateTab(selectedTab, tabs, panels) {
    tabs.forEach(tab => {
        tab.setAttribute('aria-selected', 'false');
        tab.setAttribute('tabindex', '-1');
    });
    
    panels.forEach(panel => {
        panel.hidden = true;
    });
    
    selectedTab.setAttribute('aria-selected', 'true');
    selectedTab.setAttribute('tabindex', '0');
    
    const panelId = selectedTab.getAttribute('aria-controls');
    document.getElementById(panelId).hidden = false;
}

// Add city handler
async function handleAddCity(e) {
    e.preventDefault();
    
    const input = document.getElementById('city-input');
    const countrySelect = document.getElementById('country-select');
    const cityName = input.value.trim();
    const countryCode = countrySelect ? countrySelect.value : '';
    const errorDiv = document.getElementById('city-search-error');
    
    if (!cityName) {
        showError(errorDiv, 'Please enter a city name');
        return;
    }
    
    clearError(errorDiv);
    
    try {
        const matches = await geocodeCity(cityName, countryCode);
        
        if (matches.length === 0) {
            showError(errorDiv, `No cities found for "${cityName}"`);
            return;
        }
        
        if (matches.length === 1) {
            await addCity(matches[0]);
            input.value = '';
        } else {
            currentCityMatches = matches;
            showCitySelectionDialog(cityName, matches);
        }
    } catch (error) {
        showError(errorDiv, `Error searching for city: ${error.message}`);
    }
}

// Detect user's current location
async function detectLocation() {
    const locationBtn = document.getElementById('location-btn');
    const errorDiv = document.getElementById('city-search-error');
    
    // Check if geolocation is supported
    if (!navigator.geolocation) {
        showError(errorDiv, 'Geolocation is not supported by your browser');
        return;
    }
    
    clearError(errorDiv);
    
    // Show loading state
    const originalText = locationBtn.textContent;
    locationBtn.disabled = true;
    locationBtn.textContent = 'Detecting location...';
    announceToScreenReader('Detecting your location');
    
    try {
        // Get user's coordinates
        const position = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                resolve,
                reject,
                {
                    enableHighAccuracy: false,
                    timeout: 10000,
                    maximumAge: 300000 // 5 minutes
                }
            );
        });
        
        const { latitude, longitude } = position.coords;
        announceToScreenReader('Location detected, finding city name');
        
        console.log('User coordinates:', latitude, longitude);
        
        // Reverse geocode to get city name
        const cityData = await reverseGeocode(latitude, longitude);
        
        console.log('City data from reverse geocode:', cityData);
        
        if (!cityData) {
            showError(errorDiv, 'Could not determine city name from your location');
            return;
        }
        
        // Validate cityData has required properties
        if (!cityData.display || cityData.display === 'undefined' || 
            typeof cityData.lat !== 'number' || typeof cityData.lon !== 'number' ||
            isNaN(cityData.lat) || isNaN(cityData.lon)) {
            console.error('Invalid city data received:', cityData);
            showError(errorDiv, 'Could not determine valid city from your location');
            return;
        }
        
        // Check if city already exists
        if (cities[cityData.display]) {
            announceToScreenReader(`${cityData.display} is already in your list`);
            showError(errorDiv, `${cityData.display} is already in your list`);
            return;
        }
        
        // Add the city
        await addCity(cityData);
        announceToScreenReader(`Added ${cityData.display} to your cities`);
        
    } catch (error) {
        console.error('Location detection error:', error);
        
        let errorMessage = 'Unable to detect location';
        
        if (error.code === 1) {
            errorMessage = 'Location access denied. Please enable location permissions in your browser.';
        } else if (error.code === 2) {
            errorMessage = 'Location unavailable. Please check your device settings.';
        } else if (error.code === 3) {
            errorMessage = 'Location request timed out. Please try again.';
        } else if (error.message) {
            errorMessage = `Error: ${error.message}`;
        }
        
        showError(errorDiv, errorMessage);
        announceToScreenReader(errorMessage);
        
    } finally {
        // Restore button state
        locationBtn.disabled = false;
        locationBtn.textContent = originalText;
    }
}

// Reverse geocode coordinates to city name
async function reverseGeocode(lat, lon) {
    const params = new URLSearchParams({
        lat: lat.toString(),
        lon: lon.toString(),
        format: 'json',
        addressdetails: '1'
    });
    
    // Rate limit: wait 1 second before request (Nominatim requirement)
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const response = await fetch(`https://nominatim.openstreetmap.org/reverse?${params}`, {
        headers: { 'User-Agent': 'FastWeather Web/1.0' }
    });
    
    if (!response.ok) {
        throw new Error('Failed to reverse geocode location');
    }
    
    const result = await response.json();
    
    console.log('Reverse geocode result:', result);
    
    if (!result || result.error) {
        console.error('Reverse geocode error:', result?.error);
        return null;
    }
    
    const address = result.address || {};
    
    // Helper function to safely get string value
    const getString = (value) => {
        if (value && typeof value === 'string' && value.trim() !== '') {
            return value.trim();
        }
        return null;
    };
    
    // Try different address fields for city name
    const city = getString(address.city) || 
                 getString(address.town) || 
                 getString(address.village) || 
                 getString(address.municipality) || 
                 getString(address.county);
    
    const state = getString(address.state);
    const country = getString(address.country);
    
    console.log('Extracted location:', { city, state, country });
    
    // Must have at least one valid component
    if (!city && !state && !country) {
        console.error('No valid location components found');
        return null;
    }
    
    // Build display name with only valid parts
    const displayParts = [];
    if (city) {
        displayParts.push(city);
    } else if (state) {
        displayParts.push(state); // Use state as primary if no city
    } else {
        displayParts.push(country); // Use country as fallback
    }
    
    if (city && state) {
        displayParts.push(state);
    }
    if (country) {
        displayParts.push(country);
    }
    
    const displayName = displayParts.join(', ');
    
    console.log('Final display name:', displayName);
    
    // Validate display name is not empty
    if (!displayName || displayName.trim() === '') {
        console.error('Empty display name generated');
        return null;
    }
    
    // Validate coordinates
    const latitude = parseFloat(result.lat);
    const longitude = parseFloat(result.lon);
    
    if (isNaN(latitude) || isNaN(longitude) || !isFinite(latitude) || !isFinite(longitude)) {
        console.error('Invalid coordinates:', result.lat, result.lon);
        return null;
    }
    
    // Validate coordinate ranges
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
        console.error('Coordinates out of valid range:', latitude, longitude);
        return null;
    }
    
    const cityDataObject = {
        display: displayName,
        city: city || state || country || 'Unknown',
        state: state || '',
        country: country || '',
        lat: latitude,
        lon: longitude
    };
    
    console.log('Returning city data:', cityDataObject);
    
    return cityDataObject;
}

// Geocode city
async function geocodeCity(cityName, countryCode = '') {
    const params = new URLSearchParams({
        q: cityName,
        format: 'json',
        addressdetails: '1',
        limit: '5'
    });
    
    if (countryCode) {
        params.set('countrycodes', countryCode);
    }
    
    const response = await fetch(`${NOMINATIM_URL}?${params}`, {
        headers: { 'User-Agent': 'FastWeather Web/1.0' }
    });
    
    if (!response.ok) throw new Error('Failed to search for city');
    
    const results = await response.json();
    
    return results.map(r => {
        const address = r.address || {};
        const city = address.city || address.town || address.village || cityName;
        const state = address.state || '';
        const country = address.country || '';
        const displayParts = [city, state, country].filter(p => p);
        
        return {
            display: displayParts.join(', '),
            city, state, country,
            lat: parseFloat(r.lat),
            lon: parseFloat(r.lon)
        };
    });
}

// City selection dialog
function showCitySelectionDialog(originalInput, matches) {
    const dialog = document.getElementById('city-selection-dialog');
    const listBox = document.getElementById('city-matches-list');
    const desc = document.getElementById('city-selection-desc');
    
    desc.textContent = `Multiple cities found for "${originalInput}". Please select one:`;
    
    listBox.innerHTML = '';
    matches.forEach((match, index) => {
        const option = document.createElement('div');
        option.className = 'city-option';
        option.setAttribute('role', 'option');
        option.setAttribute('id', `city-option-${index}`);
        option.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
        option.textContent = `${match.display} (${match.lat.toFixed(4)}, ${match.lon.toFixed(4)})`;
        option.dataset.index = index;
        
        option.addEventListener('click', () => {
            setActiveOption(index);
            handleCitySelection();
        });
        
        listBox.appendChild(option);
    });
    
    // Set aria-activedescendant to the first option
    listBox.setAttribute('aria-activedescendant', 'city-option-0');
    
    closeAllModals();
    focusReturnElement = document.activeElement;
    dialog.hidden = false;
    
    // Add keyboard navigation to listBox
    listBox.addEventListener('keydown', handleCityListKeydown);
    
    // Set up focus trap
    trapFocus(dialog);
    
    // Focus the listbox
    listBox.focus();
    
    // Scroll first option into view
    const firstOption = listBox.querySelector('#city-option-0');
    if (firstOption) {
        firstOption.scrollIntoView({ block: 'nearest' });
    }
}

function setActiveOption(index) {
    const listBox = document.getElementById('city-matches-list');
    const options = Array.from(listBox.querySelectorAll('.city-option'));
    
    if (index < 0 || index >= options.length) return;
    
    // Update aria-selected on all options
    options.forEach((opt, i) => {
        opt.setAttribute('aria-selected', i === index ? 'true' : 'false');
    });
    
    // Update aria-activedescendant on listbox
    listBox.setAttribute('aria-activedescendant', `city-option-${index}`);
    
    // Scroll option into view
    options[index].scrollIntoView({ block: 'nearest' });
}

function handleCityListKeydown(e) {
    const listBox = e.currentTarget;
    const options = Array.from(listBox.querySelectorAll('.city-option'));
    const currentIndex = options.findIndex(opt => opt.getAttribute('aria-selected') === 'true');
    
    let newIndex = currentIndex;
    
    switch(e.key) {
        case 'ArrowDown':
            e.preventDefault();
            newIndex = Math.min(currentIndex + 1, options.length - 1);
            if (newIndex !== currentIndex) {
                setActiveOption(newIndex);
            }
            break;
            
        case 'ArrowUp':
            e.preventDefault();
            newIndex = Math.max(currentIndex - 1, 0);
            if (newIndex !== currentIndex) {
                setActiveOption(newIndex);
            }
            break;
            
        case 'Home':
            e.preventDefault();
            setActiveOption(0);
            break;
            
        case 'End':
            e.preventDefault();
            setActiveOption(options.length - 1);
            break;
            
        case 'Enter':
            e.preventDefault();
            handleCitySelection();
            break;
            
        case ' ':
            e.preventDefault();
            handleCitySelection();
            break;
    }
}

async function handleCitySelection() {
    const selected = document.querySelector('.city-option[aria-selected="true"]');
    if (!selected) return;
    
    const index = parseInt(selected.dataset.index);
    const match = currentCityMatches[index];
    
    closeCitySelectionDialog();
    await addCity(match);
    document.getElementById('city-input').value = '';
}

function closeCitySelectionDialog() {
    const dialog = document.getElementById('city-selection-dialog');
    const listBox = document.getElementById('city-matches-list');
    
    // Remove event listener
    listBox.removeEventListener('keydown', handleCityListKeydown);
    
    // Clear aria-activedescendant
    listBox.removeAttribute('aria-activedescendant');
    
    dialog.hidden = true;
    if (focusReturnElement) {
        focusReturnElement.focus();
        focusReturnElement = null;
    }
}

// Add city to list
async function addCity(cityData, skipRender = false) {
    const key = cityData.display;
    
    console.log('addCity called:', key, 'skipRender:', skipRender);
    console.log('Current cities before add:', Object.keys(cities));
    
    if (cities[key]) {
        announceToScreenReader(`${key} is already in your list`);
        console.log('City already in list');
        return false;
    }
    
    cities[key] = [cityData.lat, cityData.lon];
    saveCitiesToStorage();
    console.log('City added to cities object, cities count:', Object.keys(cities).length);
    
    // Only render city list if not in state browsing mode
    if (!skipRender) {
        console.log('Calling renderCityList');
        renderCityList();
    } else {
        console.log('Skipping render');
    }
    
    announceToScreenReader(`${key} added to list`);
    
    // Fetch weather for new city
    console.log('Fetching weather for', key);
    try {
        await fetchWeatherForCity(key, cityData.lat, cityData.lon, false, true); // silent since we announce "added to list"
        console.log('Weather fetched for', key);
    } catch (error) {
        console.error('Failed to fetch weather for', key, error);
        announceToScreenReader(`Added ${key} but weather data unavailable`);
    }
    
    return true;
}

// Handle state/country selection
async function handleStateSelection(e) {
    e.preventDefault();
    
    const errorDiv = document.getElementById('state-selector-error');

    if (currentLocationType === 'places') {
        const categoryName = document.getElementById('places-select').value;
        if (!categoryName) {
            showError(errorDiv, 'Please select a list of places');
            return;
        }
        const category = cachedPlaceCategories.find(c => c.name === categoryName);
        if (!category || category.places.length === 0) {
            showError(errorDiv, 'Places of the World could not be loaded. Please refresh the page.');
            return;
        }
        clearError(errorDiv);
        await displayPlaces(category);
        return;
    }

    if (currentLocationType === 'us') {
        // Handle U.S. state selection
        const stateSelect = document.getElementById('state-select');
        const stateName = stateSelect.value;
        
        console.log('State selected:', stateName);
        
        if (!stateName) {
            showError(errorDiv, 'Please select a state');
            return;
        }
        
        clearError(errorDiv);
        
        // Check if cached coordinates are loaded
        if (!cachedCityCoordinates) {
            console.error('Cached US city coordinates not loaded');
            showError(errorDiv, 'City data not loaded. Please refresh the page.');
            return;
        }
        
        // Get cities for the selected state from cached data
        const stateCities = cachedCityCoordinates[stateName];
        
        if (!stateCities || stateCities.length === 0) {
            showError(errorDiv, 'No cities found for this state');
            return;
        }
        
        // Convert cached format to expected format
        const cityNames = stateCities.map(city => city.name);
        
        // Load all cities
        console.log('Loading all', cityNames.length, 'cities for', stateName);
        displayLocationCities(stateName, cityNames, cityNames.length, 'us');
    } else {
        // Handle international country selection
        const countrySelect = document.getElementById('country-select-browse');
        const countryName = countrySelect.value;
        
        console.log('Country selected:', countryName);
        
        if (!countryName) {
            showError(errorDiv, 'Please select a country');
            return;
        }
        
        clearError(errorDiv);
        
        // Check if cached coordinates are loaded
        if (!cachedInternationalCoordinates) {
            console.error('Cached international city coordinates not loaded');
            showError(errorDiv, 'City data not loaded. Please refresh the page.');
            return;
        }
        
        // Get cities for the selected country from cached data
        const countryCities = cachedInternationalCoordinates[countryName];
        
        if (!countryCities || countryCities.length === 0) {
            showError(errorDiv, 'No cities found for this country');
            return;
        }
        
        // Convert cached format to expected format
        const cityNames = countryCities.map(city => city.name);
        
        // Load all cities
        console.log('Loading all', cityNames.length, 'cities for', countryName);
        displayLocationCities(countryName, cityNames, cityNames.length, 'international');
    }
}

// Show your cities (return from state browsing)
function showYourCities() {
    const stateSelectorSection = document.querySelector('.state-selector-section');
    const cityListSection = document.querySelector('.city-list-section');
    const heading = document.getElementById('your-cities-heading');
    
    // Clear state cities tracking, and stop a Places list that's still loading
    currentStateCities = null;
    currentStateName = null;
    browseLoadGeneration++;
    browseLoading = false;
    
    // Reset heading and show state selector
    heading.textContent = 'Your Cities';
    stateSelectorSection.hidden = false;
    cityListSection.hidden = false;
    
    // Re-render the user's city list
    renderCityList();
    
    announceToScreenReader('Returned to your cities list');
}

// Display location cities (US state or international country)
async function displayLocationCities(locationName, cityNames, totalCount = null, locationType = 'us') {
    // Another list, a Places list or Back can come while this one's weather
    // loads; then this load stops rather than replacing what's showing.
    const gen = ++browseLoadGeneration;
    // Until this region's cities are in, a view switch must not show the last one's
    currentStateCities = null;
    currentStateName = null;
    browseLoading = true;
    // Hide state selector section and show city list section with location cities
    const stateSelectorSection = document.querySelector('.state-selector-section');
    const cityListSection = document.querySelector('.city-list-section');
    const heading = document.getElementById('your-cities-heading');
    const container = document.getElementById('city-list');
    
    const displayTotal = totalCount || cityNames.length;
    const locationLabel = locationType === 'us' ? 'State' : 'Country';
    
    // Keep state selector visible and update heading
    stateSelectorSection.hidden = false;
    heading.innerHTML = `Cities in ${locationName} <button id="back-to-your-cities-btn" class="back-btn">← Back to Your Cities</button>`;
    container.innerHTML = '<p class="loading-text">Loading weather data... (0/' + cityNames.length + ')</p>';
    cityListSection.hidden = false;
    
    // Add event listener for back button
    document.getElementById('back-to-your-cities-btn').addEventListener('click', () => {
        showYourCities();
    });
    
    console.log(`displayLocationCities called with ${cityNames.length} cities for ${locationName} (${locationType})`);
    
    // Select appropriate cache based on location type
    const cache = locationType === 'us' ? cachedCityCoordinates : cachedInternationalCoordinates;
    const cacheLabel = locationType === 'us' ? 'US states' : 'countries';
    
    console.log('Cached data available:', cache ? Object.keys(cache).join(', ') : 'none');
    console.log(`Looking for cached data for ${locationLabel}: "${locationName}" (length: ${locationName.length}, charCodes: ${[...locationName].map(c => c.charCodeAt(0)).join(',')})`);
    console.log(`Cache has "${locationName}":`, cache && cache[locationName] ? 'YES' : 'NO');
    
    const citiesData = [];
    
    // Check if we have cached coordinates for this location
    const useCached = cache && cache[locationName];
    
    if (useCached) {
        // Use cached coordinates - much faster!
        console.log(`✓ Using cached coordinates for ${locationName} (${cache[locationName].length} cities in cache)`);
        
        // Build city info objects with coordinates
        const cityInfos = [];
        for (const cityName of cityNames) {
            const cachedCity = cache[locationName].find(c => c.name === cityName);
            
            if (cachedCity) {
                const state = cachedCity.state || '';
                const country = locationType === 'us' ? 'United States' : locationName;
                
                // For international cities, use clean display without native state/country names
                const display = locationType === 'us' 
                    ? `${cityName}, ${state}, ${country}`
                    : `${cityName}, ${country}`;
                
                cityInfos.push({
                    name: cityName,
                    display: display,
                    state: state,
                    country: country,
                    lat: cachedCity.lat,
                    lon: cachedCity.lon,
                    weather: null
                });
            } else {
                console.warn(`City ${cityName} not found in cache`);
            }
        }
        
        // Fetch weather data for all cities in parallel
        console.log(`Fetching weather data for ${cityInfos.length} cities in parallel...`);
        const weatherPromises = cityInfos.map(async (cityInfo, index) => {
            try {
                const weather = await fetchWeatherData(cityInfo.lat, cityInfo.lon);
                cityInfo.weather = weather;
                console.log(`Loaded weather for ${cityInfo.name} (${index + 1}/${cityInfos.length})`);
            } catch (weatherError) {
                console.error(`Error fetching weather for ${cityInfo.name}:`, weatherError);
            }
            return cityInfo;
        });
        
        // Wait for all weather data to load
        const results = await Promise.all(weatherPromises);
        citiesData.push(...results);
        
        // Sort cities alphabetically by name
        citiesData.sort((a, b) => a.name.localeCompare(b.name));
        
    } else {
        // Fall back to geocoding if no cached data
        console.warn(`⚠ No cached data found for "${locationName}", falling back to geocoding (this will be slow)`);
        console.log('Possible reasons:');
        console.log('  1. JSON file not loaded (check network tab)');
        console.log('  2. Location name mismatch (check spelling/capitalization)');
        console.log('  3. Location not yet added to cache');
        if (cache) {
            console.log(`  Available ${cacheLabel}:`, Object.keys(cache));
        }
        const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
        const countryCode = locationType === 'us' ? 'us' : '';
        
        for (let i = 0; i < cityNames.length; i++) {
            const cityName = cityNames[i];
            try {
                const fullName = `${cityName}, ${locationName}`;
                const matches = await geocodeCity(fullName, countryCode);
                if (matches && matches.length > 0) {
                    const country = locationType === 'us' ? 'United States' : locationName;
                    // For international cities, use clean display format
                    const display = locationType === 'us'
                        ? matches[0].display
                        : `${cityName}, ${country}`;
                    
                    const cityInfo = {
                        name: cityName,
                        display: display,
                        state: locationType === 'us' ? locationName : '',
                        country: country,
                        lat: matches[0].lat,
                        lon: matches[0].lon,
                        weather: null
                    };
                    
                    // Fetch weather data for this city
                    try {
                        const weather = await fetchWeatherData(cityInfo.lat, cityInfo.lon);
                        cityInfo.weather = weather;
                    } catch (weatherError) {
                        console.error(`Error fetching weather for ${cityName}:`, weatherError);
                    }
                    
                    citiesData.push(cityInfo);
                }
                
                // Update progress
                container.innerHTML = `<p class="loading-text">Loading weather data... (${i + 1}/${cityNames.length})</p>`;
                
                // Rate limiting: wait 1.1 seconds between geocoding requests
                if (i < cityNames.length - 1) {
                    await delay(1100);
                }
                if (gen !== browseLoadGeneration) return;
            } catch (error) {
                console.error(`Error geocoding ${cityName}:`, error);
            }
        }
        
        // Sort cities alphabetically by name
        citiesData.sort((a, b) => a.name.localeCompare(b.name));
    }
    
    if (gen !== browseLoadGeneration) return;  // superseded while loading
    browseLoading = false;

    // Render the cities list
    console.log('Rendering', citiesData.length, 'cities');
    if (citiesData.length > 0) {
        // Store location cities for view switching
        currentStateCities = citiesData;
        currentStateName = locationName;
        
        heading.innerHTML = `Cities in ${locationName} (${citiesData.length}) <button id="back-to-your-cities-btn" class="back-btn">← Back to Your Cities</button>`;
        renderStateCitiesWithWeather(container, citiesData);
        announceToScreenReader(`Loaded ${citiesData.length} cities with weather for ${locationName}`);
        
        // Re-attach event listener for back button
        document.getElementById('back-to-your-cities-btn').addEventListener('click', () => {
            showYourCities();
        });
    } else {
        container.innerHTML = '<p class="error-message">Failed to load city data. Please try again later.</p>';
        announceToScreenReader('Failed to load city data');
    }
}

// Show a Places of the World list with each place's weather, in the same
// views as a state or country. A list can hold up to 200 places, so weather
// comes 50 places to a request rather than one request per place.
async function displayPlaces(category) {
    const stateSelectorSection = document.querySelector('.state-selector-section');
    const cityListSection = document.querySelector('.city-list-section');
    const heading = document.getElementById('your-cities-heading');
    const container = document.getElementById('city-list');
    const gen = ++browseLoadGeneration;
    // Until this list's places are in, a view switch must not show the last list
    currentStateCities = null;
    currentStateName = null;
    browseLoading = true;

    const setHeading = (text) => {
        heading.textContent = text + ' ';
        const backBtn = document.createElement('button');
        backBtn.id = 'back-to-your-cities-btn';
        backBtn.className = 'back-btn';
        backBtn.textContent = '← Back to Your Cities';
        backBtn.addEventListener('click', () => showYourCities());
        heading.appendChild(backBtn);
    };

    stateSelectorSection.hidden = false;
    cityListSection.hidden = false;
    setHeading(category.name);
    container.innerHTML = '';
    const loading = document.createElement('p');
    loading.className = 'loading-text';
    loading.textContent = `Loading weather for ${category.places.length} places...`;
    container.appendChild(loading);
    announceToScreenReader(`Loading weather for ${category.name}`);

    const placeInfos = category.places.map(placeToCityInfo);
    const batches = chunk(placeInfos, PLACES_WEATHER_BATCH);
    for (let i = 0; i < batches.length; i++) {
        if (gen !== browseLoadGeneration) return;  // another list or Back was chosen
        if (i > 0) await new Promise(resolve => setTimeout(resolve, PLACES_WEATHER_GAP_MS));
        try {
            const results = await fetchWeatherDataBatch(batches[i]);
            batches[i].forEach((info, j) => { info.weather = results[j]; });
        } catch (error) {
            console.error(`Error fetching weather for ${category.name}:`, error);
        }
    }
    if (gen !== browseLoadGeneration) return;
    browseLoading = false;

    placeInfos.sort((a, b) => a.name.localeCompare(b.name));
    currentStateCities = placeInfos;
    currentStateName = category.name;
    setHeading(`${category.name} (${placeInfos.length})`);
    renderStateCitiesWithWeather(container, placeInfos);

    const missing = placeInfos.filter(p => !p.weather).length;
    announceToScreenReader(missing
        ? `Loaded ${placeInfos.length} places for ${category.name}; weather unavailable for ${missing}`
        : `Loaded ${placeInfos.length} places with weather for ${category.name}`);
}

const PLACES_WEATHER_BATCH = 50;      // places per Open-Meteo request
const PLACES_WEATHER_GAP_MS = 500;    // pause between those requests
let browseLoadGeneration = 0;         // bumped on each browse load and on Back
let browseLoading = false;            // a browse list's weather is still loading

// Today's weather for many places in one request; one result (or null) per place
async function fetchWeatherDataBatch(locations) {
    if (locations.length === 0) return [];
    const params = new URLSearchParams({
        latitude: locations.map(l => l.lat).join(','),
        longitude: locations.map(l => l.lon).join(','),
        current: WEATHER_SUMMARY_CURRENT,
        hourly: 'cloudcover',
        daily: 'temperature_2m_max,temperature_2m_min,sunrise,sunset',
        forecast_days: '1',
        timezone: 'auto'
    });
    const response = await fetch(`${OPEN_METEO_API_URL}?${params}`);
    if (!response.ok) throw new Error('Failed to fetch weather data');
    return weatherResultsFromResponse(await response.json(), locations.length);
}

const WEATHER_SUMMARY_CURRENT = 'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,visibility';

// Helper function to fetch weather data without storing in weatherData object
async function fetchWeatherData(lat, lon) {
    const params = new URLSearchParams({
        latitude: lat,
        longitude: lon,
        current: WEATHER_SUMMARY_CURRENT,
        hourly: 'cloudcover',
        daily: 'temperature_2m_max,temperature_2m_min,sunrise,sunset',
        forecast_days: '1',
        timezone: 'auto'
    });

    const response = await fetch(`${OPEN_METEO_API_URL}?${params}`);
    if (!response.ok) throw new Error('Failed to fetch weather data');

    return await response.json();
}

// Render state cities with weather in the current view
function renderStateCitiesWithWeather(container, citiesData) {
    container.innerHTML = '';
    
    // Clean up list view controls if they exist (they're siblings, not children)
    const existingControls = document.querySelector('.list-view-controls');
    if (existingControls) {
        existingControls.remove();
    }
    
    if (currentView === 'table') {
        renderStateCitiesTableWithWeather(container, citiesData);
    } else if (currentView === 'list') {
        renderStateCitiesListWithWeather(container, citiesData);
    } else {
        renderStateCitiesFlatWithWeather(container, citiesData);
    }
}

// Add city from state selection
async function addCityFromState(cityData) {
    const added = await addCity({
        display: cityData.display,
        city: cityData.name,
        state: cityData.state || '',
        country: cityData.country || 'United States',
        lat: cityData.lat,
        lon: cityData.lon
    }, true); // Skip render - we'll stay in state view
    
    // Re-render state cities to update button states, preserving active item and scroll position
    if (added && currentStateCities && currentStateName) {
        const container = document.getElementById('city-list');
        const scrollPosition = container.scrollTop;
        const currentActive = container.getAttribute('aria-activedescendant');
        let activeIndex = 0;
        
        if (currentActive && currentActive.startsWith('state-city-item-')) {
            activeIndex = parseInt(currentActive.split('-')[3]);
        }
        
        renderStateCitiesWithWeather(container, currentStateCities);
        
        // Restore scroll position for all views
        container.scrollTop = scrollPosition;
        
        // Restore the active item after re-render for list view
        if (currentView === 'list') {
            container.setAttribute('aria-activedescendant', `state-city-item-${activeIndex}`);
            const items = container.querySelectorAll('.state-city-item');
            items.forEach((item, i) => {
                item.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
            });
            
            // Update the action button to reflect the new state
            const actionBtn = document.getElementById('state-city-action-btn');
            if (actionBtn && currentStateCities && currentStateCities[activeIndex]) {
                const cityData = currentStateCities[activeIndex];
                const isInList = cities[cityData.display];
                
                if (isInList) {
                    actionBtn.textContent = '✖ Remove from My Cities';
                    actionBtn.className = 'list-control-btn remove-btn';
                } else {
                    actionBtn.textContent = '➕ Add to My Cities';
                    actionBtn.className = 'list-control-btn';
                }
            }
        }
    }
}

// Remove city from user's list (for state browsing)
async function removeCityFromState(cityData) {
    const key = cityData.display;
    
    if (cities[key]) {
        delete cities[key];
        delete weatherData[key];
        saveCitiesToStorage();
        announceToScreenReader(`${key} removed from list`);
        
        // Re-render state cities to update button states, preserving active item and scroll position
        if (currentStateCities && currentStateName) {
            const container = document.getElementById('city-list');
            const scrollPosition = container.scrollTop;
            const currentActive = container.getAttribute('aria-activedescendant');
            let activeIndex = 0;
            
            if (currentActive && currentActive.startsWith('state-city-item-')) {
                activeIndex = parseInt(currentActive.split('-')[3]);
            }
            
            renderStateCitiesWithWeather(container, currentStateCities);
            
            // Restore scroll position for all views
            container.scrollTop = scrollPosition;
            
            // Restore the active item after re-render for list view
            if (currentView === 'list') {
                container.setAttribute('aria-activedescendant', `state-city-item-${activeIndex}`);
                const items = container.querySelectorAll('.state-city-item');
                items.forEach((item, i) => {
                    item.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
                });
                
                // Update the action button to reflect the new state
                const actionBtn = document.getElementById('state-city-action-btn');
                if (actionBtn && currentStateCities[activeIndex]) {
                    const cityData = currentStateCities[activeIndex];
                    const isInList = cities[cityData.display];
                    
                    if (isInList) {
                        actionBtn.textContent = '✖ Remove from My Cities';
                        actionBtn.className = 'list-control-btn remove-btn';
                    } else {
                        actionBtn.textContent = '➕ Add to My Cities';
                        actionBtn.className = 'list-control-btn';
                    }
                }
            }
        }
    }
}

// Render state cities with weather data in flat view
function renderStateCitiesFlatWithWeather(container, citiesData) {
    container.setAttribute('role', 'list');
    
    citiesData.forEach((cityData) => {
        const card = document.createElement('article');
        card.className = 'city-card state-city-card';
        card.setAttribute('role', 'listitem');
        
        const header = document.createElement('div');
        header.className = 'city-card-header';
        
        const title = document.createElement('h4');
        title.textContent = cityData.label || cityData.display;
        header.appendChild(title);
        card.appendChild(header);

        // A place from Places of the World: where it is and why it's known
        if (cityData.location) {
            const where = document.createElement('p');
            where.className = 'place-location';
            where.textContent = cityData.location;
            card.appendChild(where);
        }
        if (cityData.note) {
            const note = document.createElement('p');
            note.className = 'place-note';
            note.textContent = cityData.note;
            card.appendChild(note);
        }
        
        const content = document.createElement('div');
        content.className = 'city-card-content';
        
        if (cityData.weather && cityData.weather.current) {
            const current = cityData.weather.current;
            const weatherDesc = WEATHER_CODES[current.weather_code] || 'Unknown';
            
            const summary = document.createElement('div');
            summary.className = 'weather-summary';
            
            const details = document.createElement('dl');
            details.className = 'weather-details';
            
            const forecastDetails = document.createElement('dl');
            let hasForecastData = false;
            
            // Render fields in custom order
            currentConfig.cityListOrder.forEach(key => {
                if (!currentConfig.cityList[key]) return;
                
                switch(key) {
                    case 'temperature':
                        const temp = convertTemperature(current.temperature_2m);
                        const tempSpan = document.createElement('span');
                        tempSpan.className = 'temperature';
                        tempSpan.textContent = `${temp}°${currentConfig.units.temperature}`;
                        summary.appendChild(tempSpan);
                        break;
                        
                    case 'conditions':
                        const descSpan = document.createElement('span');
                        descSpan.className = 'weather-desc';
                        descSpan.textContent = weatherDesc;
                        summary.appendChild(descSpan);
                        break;
                        
                    case 'feels_like':
                        addDetail(details, 'Feels Like', `${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}`);
                        break;
                        
                    case 'humidity':
                        addDetail(details, 'Humidity', `${current.relative_humidity_2m}%`);
                        break;
                        
                    case 'wind_speed':
                        const windSpeed = convertWindSpeed(current.wind_speed_10m);
                        addDetail(details, 'Wind Speed', `${windSpeed} ${currentConfig.units.wind_speed}`);
                        break;
                        
                    case 'wind_direction':
                        const cardinal = degreesToCardinal(current.wind_direction_10m);
                        addDetail(details, 'Wind Direction', `${cardinal} (${current.wind_direction_10m}°)`);
                        break;
                        
                    case 'high_temp':
                        if (cityData.weather.daily) {
                            addDetail(forecastDetails, 'High', `${convertTemperature(cityData.weather.daily.temperature_2m_max[0])}°${currentConfig.units.temperature}`);
                            hasForecastData = true;
                        }
                        break;
                        
                    case 'low_temp':
                        if (cityData.weather.daily) {
                            addDetail(forecastDetails, 'Low', `${convertTemperature(cityData.weather.daily.temperature_2m_min[0])}°${currentConfig.units.temperature}`);
                            hasForecastData = true;
                        }
                        break;
                        
                    case 'sunrise':
                        if (cityData.weather.daily && cityData.weather.daily.sunrise && cityData.weather.daily.sunrise[0]) {
                            const sunriseTime = new Date(cityData.weather.daily.sunrise[0]);
                            addDetail(forecastDetails, 'Sunrise', sunriseTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }));
                            hasForecastData = true;
                        }
                        break;
                        
                    case 'sunset':
                        if (cityData.weather.daily && cityData.weather.daily.sunset && cityData.weather.daily.sunset[0]) {
                            const sunsetTime = new Date(cityData.weather.daily.sunset[0]);
                            addDetail(forecastDetails, 'Sunset', sunsetTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }));
                            hasForecastData = true;
                        }
                        break;
                }
            });
            
            content.appendChild(summary);
            
            if (details.children.length > 0) {
                content.appendChild(details);
            }
            
            if (hasForecastData) {
                const forecast = document.createElement('div');
                forecast.className = 'daily-forecast';
                
                const forecastTitle = document.createElement('h5');
                forecastTitle.textContent = 'Today';
                forecast.appendChild(forecastTitle);
                forecast.appendChild(forecastDetails);
                content.appendChild(forecast);
            }
        } else {
            content.innerHTML = '<p class="loading-text">No weather data available</p>';
        }
        
        card.appendChild(content);
        
        const controls = document.createElement('div');
        controls.className = 'city-card-controls';
        
        // Check if city is already in user's list
        const isInList = cities[cityData.display];
        
        if (isInList) {
            const removeBtn = createButton('✖ Remove from List', `Remove ${cityData.display} from your cities list`, async () => {
                await removeCityFromState(cityData);
            });
            removeBtn.className = 'remove-btn';
            controls.appendChild(removeBtn);
        } else {
            const addBtn = createButton('➕ Add to My Cities', `Add ${cityData.display} to your cities list`, async () => {
                await addCityFromState(cityData);
            });
            addBtn.className = 'add-city-btn';
            controls.appendChild(addBtn);
        }
        
        card.appendChild(controls);
        container.appendChild(card);
    });
}

// Render state cities with weather in table view
function renderStateCitiesTableWithWeather(container, citiesData) {
    container.setAttribute('role', 'region');
    
    const table = document.createElement('table');
    table.className = 'weather-table';
    
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    const cityHeader = document.createElement('th');
    cityHeader.textContent = 'City';
    cityHeader.scope = 'col';
    headerRow.appendChild(cityHeader);
    
    const columnConfig = [
        { key: 'temperature', label: 'Temperature' },
        { key: 'conditions', label: 'Conditions' },
        { key: 'uv_index', label: 'UV Index' },
        { key: 'feels_like', label: 'Feels Like' },
        { key: 'humidity', label: 'Humidity' },
        { key: 'wind_speed', label: 'Wind Speed' },
        { key: 'wind_gusts', label: 'Wind Gusts' },
        { key: 'wind_direction', label: 'Wind Direction' },
        { key: 'high_temp', label: 'High' },
        { key: 'low_temp', label: 'Low' },
        { key: 'sunrise', label: 'Sunrise' },
        { key: 'sunset', label: 'Sunset' }
    ];
    
    columnConfig.forEach(col => {
        if (currentConfig.cityList[col.key]) {
            const th = document.createElement('th');
            th.textContent = col.label;
            th.scope = 'col';
            headerRow.appendChild(th);
        }
    });

    // Places of the World lists say where each place is and why it's known
    const hasAbout = citiesData.some(c => c.location || c.note);
    if (hasAbout) {
        const aboutHeader = document.createElement('th');
        aboutHeader.textContent = 'About';
        aboutHeader.scope = 'col';
        headerRow.appendChild(aboutHeader);
    }

    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = 'Actions';
    actionsHeader.scope = 'col';
    headerRow.appendChild(actionsHeader);
    
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    const tbody = document.createElement('tbody');
    
    citiesData.forEach((cityData) => {
        const row = document.createElement('tr');
        
        const cityCell = document.createElement('th');
        cityCell.scope = 'row';
        cityCell.textContent = cityData.label || cityData.display;
        row.appendChild(cityCell);
        
        if (cityData.weather && cityData.weather.current) {
            const current = cityData.weather.current;
            const weather = cityData.weather;
            
            // Add cells based on config order
            currentConfig.cityListOrder.forEach(key => {
                if (!currentConfig.cityList[key]) return;
                
                const cell = document.createElement('td');
                
                switch(key) {
                    case 'temperature':
                        cell.textContent = `${convertTemperature(current.temperature_2m)}°${currentConfig.units.temperature}`;
                        break;
                    case 'conditions':
                        cell.textContent = WEATHER_CODES[current.weather_code] || 'Unknown';
                        break;
                    case 'feels_like':
                        cell.textContent = `${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}`;
                        break;
                    case 'humidity':
                        cell.textContent = `${current.relative_humidity_2m}%`;
                        break;
                    case 'wind_speed':
                        const windSpeed = convertWindSpeed(current.wind_speed_10m);
                        cell.textContent = `${windSpeed} ${currentConfig.units.wind_speed}`;
                        break;
                    case 'wind_gusts':
                        if (current.wind_gusts_10m) {
                            const gusts = convertWindSpeed(current.wind_gusts_10m);
                            cell.textContent = `${gusts} ${currentConfig.units.wind_speed}`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'wind_direction':
                        const windDir = degreesToCardinal(current.wind_direction_10m);
                        cell.textContent = `${windDir} (${current.wind_direction_10m}°)`;
                        break;
                    case 'uv_index':
                        if (current.uv_index !== null && current.uv_index !== undefined) {
                            const { category } = getUVIndexCategory(current.uv_index);
                            cell.textContent = `${Math.round(current.uv_index)} (${category})`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'high_temp':
                        if (weather.daily && weather.daily.temperature_2m_max) {
                            cell.textContent = `${convertTemperature(weather.daily.temperature_2m_max[0])}°${currentConfig.units.temperature}`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'low_temp':
                        if (weather.daily && weather.daily.temperature_2m_min) {
                            cell.textContent = `${convertTemperature(weather.daily.temperature_2m_min[0])}°${currentConfig.units.temperature}`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'sunrise':
                        if (weather.daily && weather.daily.sunrise && weather.daily.sunrise[0]) {
                            const sunriseTime = new Date(weather.daily.sunrise[0]);
                            cell.textContent = sunriseTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'sunset':
                        if (weather.daily && weather.daily.sunset && weather.daily.sunset[0]) {
                            const sunsetTime = new Date(weather.daily.sunset[0]);
                            cell.textContent = sunsetTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                }
                
                row.appendChild(cell);
            });
        } else {
            const enabledColumns = columnConfig.filter(col => currentConfig.cityList[col.key]).length;
            for (let i = 0; i < enabledColumns; i++) {
                const loadingCell = document.createElement('td');
                loadingCell.textContent = 'N/A';
                row.appendChild(loadingCell);
            }
        }

        if (hasAbout) {
            const aboutCell = document.createElement('td');
            aboutCell.textContent = [cityData.location, cityData.note].filter(Boolean).join('. ');
            row.appendChild(aboutCell);
        }

        const actionsCell = document.createElement('td');
        
        const isInList = cities[cityData.display];
        
        if (isInList) {
            const removeBtn = createButton('✖ Remove', `Remove ${cityData.display} from your cities list`, async () => {
                await removeCityFromState(cityData);
            });
            removeBtn.className = 'remove-btn-small';
            actionsCell.appendChild(removeBtn);
        } else {
            const addBtn = createButton('➕ Add', `Add ${cityData.display} to your cities list`, async () => {
                await addCityFromState(cityData);
            });
            addBtn.className = 'add-city-btn-small';
            actionsCell.appendChild(addBtn);
        }
        
        row.appendChild(actionsCell);
        
        tbody.appendChild(row);
    });
    
    table.appendChild(tbody);
    container.appendChild(table);
}

// Render state cities with weather in list view
function renderStateCitiesListWithWeather(container, citiesData) {
    container.setAttribute('role', 'listbox');
    container.setAttribute('tabindex', '0');
    container.removeAttribute('aria-label');
    
    citiesData.forEach((cityData, index) => {
        const item = document.createElement('div');
        item.className = 'list-view-item state-city-item';
        item.setAttribute('role', 'option');
        item.id = `state-city-item-${index}`;
        item.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
        
        let weatherText = cityData.label || cityData.display;
        if (cityData.weather && cityData.weather.current) {
            const current = cityData.weather.current;
            const weather = cityData.weather;
            const parts = [];
            
            // Add data in custom order
            currentConfig.cityListOrder.forEach(key => {
                if (!currentConfig.cityList[key]) return;
                
                switch(key) {
                    case 'temperature':
                        const temp = convertTemperature(current.temperature_2m);
                        parts.push(`${temp}°${currentConfig.units.temperature}`);
                        break;
                    case 'conditions':
                        const weatherDesc = WEATHER_CODES[current.weather_code] || 'Unknown';
                        parts.push(weatherDesc);
                        break;
                    case 'feels_like':
                        const feels = convertTemperature(current.apparent_temperature);
                        parts.push(`Feels: ${feels}°${currentConfig.units.temperature}`);
                        break;
                    case 'humidity':
                        parts.push(`Humidity: ${current.relative_humidity_2m}%`);
                        break;
                    case 'wind_speed':
                        const windSpeed = convertWindSpeed(current.wind_speed_10m);
                        parts.push(`Wind: ${windSpeed} ${currentConfig.units.wind_speed}`);
                        break;
                    case 'wind_direction':
                        const windDir = degreesToCardinal(current.wind_direction_10m);
                        parts.push(`Wind Dir: ${windDir}`);
                        break;
                    case 'high_temp':
                        if (weather.daily) {
                            const high = convertTemperature(weather.daily.temperature_2m_max[0]);
                            parts.push(`High: ${high}°${currentConfig.units.temperature}`);
                        }
                        break;
                    case 'low_temp':
                        if (weather.daily) {
                            const low = convertTemperature(weather.daily.temperature_2m_min[0]);
                            parts.push(`Low: ${low}°${currentConfig.units.temperature}`);
                        }
                        break;
                    case 'sunrise':
                        if (weather.daily && weather.daily.sunrise && weather.daily.sunrise[0]) {
                            const sunriseTime = new Date(weather.daily.sunrise[0]);
                            parts.push(`Sunrise: ${sunriseTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`);
                        }
                        break;
                    case 'sunset':
                        if (weather.daily && weather.daily.sunset && weather.daily.sunset[0]) {
                            const sunsetTime = new Date(weather.daily.sunset[0]);
                            parts.push(`Sunset: ${sunsetTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`);
                        }
                        break;
                }
            });
            
            weatherText = `${cityData.label || cityData.display} - ${parts.join(', ')}`;
        } else if (cityData.location || cityData.note) {
            weatherText = `${cityData.label || cityData.display} - weather unavailable`;
        }

        // A place: name and weather first, then where it is and why it's known
        const about = [cityData.location, cityData.note].filter(Boolean).join('. ');
        if (about) {
            weatherText += `. ${about}`;
        }
        
        // Just show the text - buttons will be displayed after the list
        item.textContent = weatherText;
        
        // Set aria-label for screen reader
        item.setAttribute('aria-label', weatherText);
        
        container.appendChild(item);
    });
    
    container.setAttribute('aria-activedescendant', 'state-city-item-0');
    
    // Add control button for adding/removing the selected city
    const controlsDiv = document.createElement('div');
    controlsDiv.className = 'list-view-controls';
    
    const actionBtn = createButton('➕ Add to My Cities', 'Add selected city to your cities list', () => {
        const items = container.querySelectorAll('.state-city-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        let activeIndex = 0;
        
        if (currentActive && currentActive.startsWith('state-city-item-')) {
            activeIndex = parseInt(currentActive.split('-')[3]);
        }
        
        if (citiesData[activeIndex]) {
            const cityData = citiesData[activeIndex];
            const isInList = cities[cityData.display];
            
            if (isInList) {
                removeCityFromState(cityData);
            } else {
                addCityFromState(cityData);
            }
        }
    });
    actionBtn.className = 'list-control-btn';
    actionBtn.id = 'state-city-action-btn';
    controlsDiv.appendChild(actionBtn);
    
    container.parentElement.insertBefore(controlsDiv, container.nextSibling);
    
    // Function to update the action button based on current selection
    const updateActionButton = (index) => {
        if (citiesData[index]) {
            const cityData = citiesData[index];
            const isInList = cities[cityData.display];
            
            if (isInList) {
                actionBtn.textContent = '✖ Remove from My Cities';
                actionBtn.className = 'list-control-btn remove-btn';
            } else {
                actionBtn.textContent = '➕ Add to My Cities';
                actionBtn.className = 'list-control-btn';
            }
        }
    };
    
    // Set initial button state
    updateActionButton(0);
    
    // Remove old keyboard navigation handler if exists
    if (container._stateCityNavHandler) {
        container.removeEventListener('keydown', container._stateCityNavHandler);
    }
    
    // Add keyboard navigation for state cities list
    const stateCityNavHandler = (e) => {
        const items = container.querySelectorAll('.state-city-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        let activeIndex = 0;
        
        // Parse the index from the current active descendant
        if (currentActive && currentActive.startsWith('state-city-item-')) {
            activeIndex = parseInt(currentActive.split('-')[3]);
        }
        
        let handled = false;
        let newIndex = activeIndex;
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (activeIndex < items.length - 1) {
                    newIndex = activeIndex + 1;
                }
                handled = true;
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (activeIndex > 0) {
                    newIndex = activeIndex - 1;
                }
                handled = true;
                break;
                
            case 'Home':
                e.preventDefault();
                newIndex = 0;
                handled = true;
                break;
                
            case 'End':
                e.preventDefault();
                newIndex = items.length - 1;
                handled = true;
                break;
                
            case 'Enter':
            case ' ':
                // Activate the add/remove action for the selected city
                e.preventDefault();
                if (citiesData[activeIndex]) {
                    const cityData = citiesData[activeIndex];
                    const isInList = cities[cityData.display];
                    
                    if (isInList) {
                        removeCityFromState(cityData);
                    } else {
                        addCityFromState(cityData);
                    }
                }
                handled = true;
                break;
        }
        
        if (handled && newIndex !== activeIndex) {
            // Update aria-selected on all items
            items.forEach((item, i) => {
                item.setAttribute('aria-selected', i === newIndex ? 'true' : 'false');
            });
            
            // Update aria-activedescendant
            container.setAttribute('aria-activedescendant', `state-city-item-${newIndex}`);
            
            // Scroll item into view
            items[newIndex].scrollIntoView({ block: 'nearest' });
            
            // Update the action button text based on new selection
            updateActionButton(newIndex);
            
            // Announce the new item to screen readers
            if (items[newIndex]) {
                announceToScreenReader(items[newIndex].textContent);
            }
        }
    };
    
    container._stateCityNavHandler = stateCityNavHandler;
    container.addEventListener('keydown', stateCityNavHandler);
}

// Fetch weather data
async function fetchWeatherForCity(cityName, lat, lon, detailed = false, silent = false) {
    try {
        const params = new URLSearchParams({
            latitude: lat,
            longitude: lon,
            current: 'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility,uv_index,dewpoint_2m',
            timezone: 'auto'
        });
        
        if (detailed) {
            params.append('hourly', 'temperature_2m,apparent_temperature,relative_humidity_2m,dewpoint_2m,precipitation,precipitation_probability,weathercode,cloudcover,windspeed_10m,windgusts_10m,uv_index');
            params.append('daily', 'weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_sum,precipitation_probability_max,windspeed_10m_max,uv_index_max,daylight_duration,sunshine_duration');
            params.append('forecast_days', '16');
        } else {
            params.append('hourly', 'cloudcover,uv_index,precipitation_probability');
            params.append('daily', 'temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,precipitation_probability_max');
            params.append('forecast_days', '1');
        }
        
        const response = await fetch(`${OPEN_METEO_API_URL}?${params}`);
        if (!response.ok) throw new Error('Failed to fetch weather data');
        
        const data = await response.json();
        weatherData[cityName] = data;
        
        renderCityList();
        
        if (!silent) {
            announceToScreenReader(`Weather data updated for ${cityName}`);
        }
        
        return data;
    } catch (error) {
        console.error(`Error fetching weather for ${cityName}:`, error);
        if (!silent) {
            announceToScreenReader(`Failed to fetch weather for ${cityName}`);
        }
        throw error;
    }
}

// Render city list
function renderCityList() {
    console.log('renderCityList called, cities count:', Object.keys(cities).length);
    console.log('Current view:', currentView);
    console.log('City keys:', Object.keys(cities));
    
    const container = document.getElementById('city-list');
    const emptyState = document.getElementById('empty-state');
    
    if (!container) {
        console.error('city-list container not found!');
        return;
    }
    
    if (Object.keys(cities).length === 0) {
        console.log('No cities, showing empty state');
        container.innerHTML = '';
        emptyState.hidden = false;
        // Clean up list view controls if they exist
        const existingControls = document.querySelector('.list-view-controls');
        if (existingControls) {
            existingControls.remove();
        }
        return;
    }
    
    console.log('Cities exist, rendering');
    emptyState.hidden = true;
    container.innerHTML = '';
    
    // Remove any existing list navigation handler
    if (listNavigationHandler) {
        container.removeEventListener('keydown', listNavigationHandler);
        listNavigationHandler = null;
    }
    
    // Clean up list view controls if they exist
    const existingControls = document.querySelector('.list-view-controls');
    if (existingControls) {
        existingControls.remove();
    }
    
    // Render based on current view
    if (currentView === 'table') {
        console.log('Rendering table view');
        renderTableView(container);
    } else if (currentView === 'list') {
        console.log('Rendering list view');
        renderListView(container);
    } else {
        console.log('Rendering flat view');
        renderFlatView(container);
    }
    
    console.log('renderCityList completed, container children:', container.children.length);
}

// View menu functions
function toggleViewMenu() {
    const viewMenu = document.getElementById('view-menu');
    const viewMenuBtn = document.getElementById('view-menu-btn');
    const isExpanded = viewMenuBtn.getAttribute('aria-expanded') === 'true';
    
    if (isExpanded) {
        closeViewMenu();
    } else {
        openViewMenu();
    }
}

function openViewMenu() {
    const viewMenu = document.getElementById('view-menu');
    const viewMenuBtn = document.getElementById('view-menu-btn');
    
    viewMenu.hidden = false;
    viewMenuBtn.setAttribute('aria-expanded', 'true');
    
    // Focus first menu item
    const firstItem = viewMenu.querySelector('[role="menuitem"]');
    if (firstItem) {
        firstItem.focus();
    }
}

function closeViewMenu() {
    const viewMenu = document.getElementById('view-menu');
    const viewMenuBtn = document.getElementById('view-menu-btn');
    
    viewMenu.hidden = true;
    viewMenuBtn.setAttribute('aria-expanded', 'false');
}

function handleViewMenuKeydown(e) {
    const items = Array.from(e.currentTarget.querySelectorAll('[role="menuitem"]'));
    const currentIndex = items.indexOf(document.activeElement);
    
    let handled = false;
    
    switch(e.key) {
        case 'ArrowDown':
            e.preventDefault();
            const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
            items[nextIndex].focus();
            handled = true;
            break;
            
        case 'ArrowUp':
            e.preventDefault();
            const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
            items[prevIndex].focus();
            handled = true;
            break;
            
        case 'Home':
            e.preventDefault();
            items[0].focus();
            handled = true;
            break;
            
        case 'End':
            e.preventDefault();
            items[items.length - 1].focus();
            handled = true;
            break;
            
        case 'Enter':
        case ' ':
            e.preventDefault();
            if (document.activeElement && document.activeElement.dataset.view) {
                const view = document.activeElement.dataset.view;
                switchView(view);
                closeViewMenu();
                document.getElementById('view-menu-btn').focus();
            }
            handled = true;
            break;
    }
}

// View switcher
function switchView(view) {
    currentView = view;
    
    // Save the view preference
    currentConfig.defaultView = view;
    saveConfigToStorage();
    
    // Update menu item states
    document.querySelectorAll('#view-menu [role="menuitem"]').forEach(item => {
        const isSelected = item.dataset.view === view;
        item.setAttribute('aria-checked', isSelected ? 'true' : 'false');
    });
    
    // Update button label
    const viewLabel = view.charAt(0).toUpperCase() + view.slice(1);
    document.getElementById('current-view-label').textContent = `View: ${viewLabel}`;
    
    // Re-render with new view - check if viewing state cities or user cities
    if (browseLoading) {
        // A state, country or Places list is still loading: it renders in the
        // new view when it's in, and the loading message stays until then
    } else if (currentStateCities && currentStateName) {
        // Re-render state cities with new view
        const container = document.getElementById('city-list');
        renderStateCitiesWithWeather(container, currentStateCities);
    } else {
        // Re-render user cities with new view
        renderCityList();
    }
    announceToScreenReader(`Switched to ${view} view`);
}

// Flat view (original card-based layout)
function renderFlatView(container) {
    container.setAttribute('role', 'list');
    container.removeAttribute('tabindex');
    container.removeAttribute('aria-activedescendant');
    
    Object.keys(cities).forEach((cityName, index) => {
        const [lat, lon] = cities[cityName];
        const weather = weatherData[cityName];
        
        const cityCard = createCityCard(cityName, lat, lon, weather, index);
        container.appendChild(cityCard);
    });
}

// Create city card
function createCityCard(cityName, lat, lon, weather, index) {
    const card = document.createElement('article');
    card.className = 'city-card';
    card.setAttribute('role', 'listitem');
    
    const header = document.createElement('div');
    header.className = 'city-card-header';
    
    const titleButton = document.createElement('button');
    titleButton.className = 'city-title-btn';
    titleButton.addEventListener('click', () => showFullWeather(cityName, lat, lon));
    
    const title = document.createElement('h3');
    title.textContent = cityName;
    titleButton.appendChild(title);
    
    header.appendChild(titleButton);
    card.appendChild(header);
    
    // Weather content
    const content = document.createElement('div');
    content.className = 'city-card-content';
    
    if (weather) {
        const current = weather.current;
        const weatherDesc = WEATHER_CODES[current.weather_code] || 'Unknown';
        
        const summary = document.createElement('div');
        summary.className = 'weather-summary';
        
        const details = document.createElement('dl');
        details.className = 'weather-details';
        
        const forecastDetails = document.createElement('dl');
        let hasForecastData = false;
        
        // Render fields in custom order
        currentConfig.cityListOrder.forEach(key => {
            if (!currentConfig.cityList[key]) return;
            
            switch(key) {
                case 'temperature':
                    const temp = convertTemperature(current.temperature_2m);
                    const tempSpan = document.createElement('span');
                    tempSpan.className = 'temperature';
                    tempSpan.textContent = `${temp}°${currentConfig.units.temperature}`;
                    summary.appendChild(tempSpan);
                    break;
                    
                case 'conditions':
                    const descSpan = document.createElement('span');
                    descSpan.className = 'weather-desc';
                    descSpan.textContent = weatherDesc;
                    summary.appendChild(descSpan);
                    break;
                    
                case 'feels_like':
                    addDetail(details, 'Feels Like', `${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}`);
                    break;
                    
                case 'humidity':
                    addDetail(details, 'Humidity', `${current.relative_humidity_2m}%`);
                    break;
                    
                case 'wind_speed':
                    const windSpeed = convertWindSpeed(current.wind_speed_10m);
                    let windText = `${windSpeed} ${currentConfig.units.wind_speed}`;
                    if (currentConfig.cityList.wind_gusts && current.wind_gusts_10m) {
                        const gusts = convertWindSpeed(current.wind_gusts_10m);
                        windText += `, gusts ${gusts} ${currentConfig.units.wind_speed}`;
                    }
                    addDetail(details, 'Wind', windText);
                    break;
                    
                case 'wind_direction':
                    const cardinal = degreesToCardinal(current.wind_direction_10m);
                    addDetail(details, 'Wind Direction', `${cardinal} (${current.wind_direction_10m}°)`);
                    break;
                    
                case 'wind_gusts':
                    // Only show if not already shown with wind_speed
                    if (!currentConfig.cityList.wind_speed && current.wind_gusts_10m) {
                        const gusts = convertWindSpeed(current.wind_gusts_10m);
                        addDetail(details, 'Wind Gusts', `${gusts} ${currentConfig.units.wind_speed}`);
                    }
                    break;
                    
                case 'uv_index':
                    if (current.uv_index !== null && current.uv_index !== undefined) {
                        const { category, color } = getUVIndexCategory(current.uv_index);
                        const uvBadge = document.createElement('span');
                        uvBadge.className = 'uv-badge';
                        uvBadge.style.backgroundColor = color;
                        uvBadge.style.color = current.uv_index <= 5 ? '#000' : '#fff';
                        uvBadge.textContent = `UV: ${Math.round(current.uv_index)} (${category})`;
                        uvBadge.setAttribute('aria-label', getUVIndexDescription(current.uv_index));
                        summary.appendChild(uvBadge);
                    }
                    break;
                    
                case 'high_temp':
                    if (weather.daily) {
                        addDetail(forecastDetails, 'High', `${convertTemperature(weather.daily.temperature_2m_max[0])}°${currentConfig.units.temperature}`);
                        hasForecastData = true;
                    }
                    break;
                    
                case 'low_temp':
                    if (weather.daily) {
                        addDetail(forecastDetails, 'Low', `${convertTemperature(weather.daily.temperature_2m_min[0])}°${currentConfig.units.temperature}`);
                        hasForecastData = true;
                    }
                    break;
                    
                case 'sunrise':
                    if (weather.daily && weather.daily.sunrise && weather.daily.sunrise[0]) {
                        const sunriseTime = new Date(weather.daily.sunrise[0]);
                        const sunriseFormatted = sunriseTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        addDetail(forecastDetails, 'Sunrise', sunriseFormatted);
                        hasForecastData = true;
                    }
                    break;
                    
                case 'sunset':
                    if (weather.daily && weather.daily.sunset && weather.daily.sunset[0]) {
                        const sunsetTime = new Date(weather.daily.sunset[0]);
                        const sunsetFormatted = sunsetTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        addDetail(forecastDetails, 'Sunset', sunsetFormatted);
                        hasForecastData = true;
                    }
                    break;
            }
        });
        
        content.appendChild(summary);
        
        if (details.children.length > 0) {
            content.appendChild(details);
        }
        
        if (hasForecastData) {
            const forecast = document.createElement('div');
            forecast.className = 'daily-forecast';
            
            const forecastTitle = document.createElement('h4');
            forecastTitle.textContent = 'Today';
            forecast.appendChild(forecastTitle);
            forecast.appendChild(forecastDetails);
            content.appendChild(forecast);
        }
    } else {
        content.innerHTML = '<p class="loading-text">Loading weather data...</p>';
    }
    
    card.appendChild(content);
    
    // Feature action buttons
    const featureActions = document.createElement('div');
    featureActions.className = 'feature-actions';
    
    // Historical Weather button
    const historyBtn = createButton(
        '<span class="icon">📊</span> History',
        () => showHistoricalWeather(cityName, lat, lon)
    );
    historyBtn.className = 'feature-btn';
    historyBtn.setAttribute('aria-label', `View historical weather for ${cityName}`);
    featureActions.appendChild(historyBtn);
    
    // Expected Precipitation button
    const precipBtn = createButton(
        '<span class="icon">💧</span> Precipitation',
        () => showPrecipitationNowcast(cityName, lat, lon)
    );
    precipBtn.className = 'feature-btn';
    precipBtn.setAttribute('aria-label', `View precipitation forecast for ${cityName}`);
    featureActions.appendChild(precipBtn);
    
    // Weather Around Me button
    const aroundBtn = createButton(
        '<span class="icon">🧭</span> Around Me',
        () => showWeatherAroundMe(cityName, lat, lon)
    );
    aroundBtn.className = 'feature-btn';
    aroundBtn.setAttribute('aria-label', `View weather around ${cityName}`);
    featureActions.appendChild(aroundBtn);
    
    // Weather Alert badge
    const alertContainer = document.createElement('span');
    alertContainer.id = `alert-badge-${index}`;
    alertContainer.className = 'alert-container';
    featureActions.appendChild(alertContainer);

    // Render immediately from cache if available; otherwise fetch async.
    // Use document.getElementById at resolve time (not the captured reference) so
    // the badge lands in the current DOM even if renderCityList() rebuilt the cards
    // while the NWS request was in flight.
    const _flatCached = alertsCache[cityName];
    if (_flatCached && (Date.now() - _flatCached.timestamp < 600000)) {
        alertContainer.innerHTML = renderAlertBadge(_flatCached.alerts);
    } else {
        const _flatBadgeId = `alert-badge-${index}`;
        fetchWeatherAlerts(cityName, lat, lon).then(alerts => {
            const el = document.getElementById(_flatBadgeId);
            if (el) el.innerHTML = renderAlertBadge(alerts);
        });
    }
    
    card.appendChild(featureActions);
    
    // Controls at the bottom for better screen reader experience
    const controls = document.createElement('div');
    controls.className = 'city-card-controls';
    
    // Move up button
    if (index > 0) {
        const upBtn = createButton('↑', `Move ${cityName} up in list`, () => moveCityUp(cityName));
        upBtn.className = 'icon-btn';
        controls.appendChild(upBtn);
    }
    
    // Move down button
    if (index < Object.keys(cities).length - 1) {
        const downBtn = createButton('↓', `Move ${cityName} down in list`, () => moveCityDown(cityName));
        downBtn.className = 'icon-btn';
        controls.appendChild(downBtn);
    }
    
    // Remove button
    const removeBtn = createButton('🗑️', `Remove ${cityName} from list`, () => removeCity(cityName));
    removeBtn.className = 'icon-btn remove-btn';
    controls.appendChild(removeBtn);
    
    card.appendChild(controls);
    
    return card;
}

function addDetail(dl, label, value) {
    const dt = document.createElement('dt');
    dt.textContent = label + ':';
    const dd = document.createElement('dd');
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
}

function createButton(text, ariaLabelOrOnClick, onClickIfThreeParams = null) {
    const btn = document.createElement('button');
    btn.innerHTML = text;
    
    // Handle both old signature (text, ariaLabel, onClick) and new signature (text, onClick, ariaLabel)
    let onClick, ariaLabel;
    if (typeof ariaLabelOrOnClick === 'function') {
        // New signature: (text, onClick, ariaLabel?)
        onClick = ariaLabelOrOnClick;
        ariaLabel = onClickIfThreeParams;
    } else {
        // Old signature: (text, ariaLabel, onClick)
        ariaLabel = ariaLabelOrOnClick;
        onClick = onClickIfThreeParams;
    }
    
    if (ariaLabel && typeof ariaLabel === 'string') {
        btn.setAttribute('aria-label', ariaLabel);
    }
    
    if (onClick) {
        btn.addEventListener('click', onClick);
    }
    
    return btn;
}

// Table view
function renderTableView(container) {
    container.removeAttribute('role');
    container.removeAttribute('tabindex');
    container.removeAttribute('aria-activedescendant');
    
    const table = document.createElement('table');
    table.className = 'weather-table';
    
    // Table header - dynamically build based on config
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    // City column always present
    const cityHeader = document.createElement('th');
    cityHeader.textContent = 'City';
    cityHeader.scope = 'col';
    headerRow.appendChild(cityHeader);
    
    // Label mapping for column headers
    const columnLabels = {
        'temperature': 'Temperature',
        'conditions': 'Conditions',
        'uv_index': 'UV Index',
        'feels_like': 'Feels Like',
        'humidity': 'Humidity',
        'wind_speed': 'Wind Speed',
        'wind_gusts': 'Wind Gusts',
        'wind_direction': 'Wind Direction',
        'high_temp': 'High',
        'low_temp': 'Low',
        'sunrise': 'Sunrise',
        'sunset': 'Sunset'
    };
    
    // Add headers based on config order (must match data order)
    currentConfig.cityListOrder.forEach(key => {
        if (currentConfig.cityList[key] && columnLabels[key]) {
            const th = document.createElement('th');
            th.textContent = columnLabels[key];
            th.scope = 'col';
            headerRow.appendChild(th);
        }
    });
    
    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = 'Actions';
    actionsHeader.scope = 'col';
    headerRow.appendChild(actionsHeader);
    
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Table body
    const tbody = document.createElement('tbody');
    
    Object.keys(cities).forEach((cityName, index) => {
        const [lat, lon] = cities[cityName];
        const weather = weatherData[cityName];
        
        const row = document.createElement('tr');
        
        // City name (row header)
        const cityCell = document.createElement('th');
        cityCell.scope = 'row';
        
        // Make city name a clickable link
        const cityLink = document.createElement('a');
        cityLink.href = '#';
        cityLink.textContent = cityName;
        cityLink.className = 'city-link';
        cityLink.addEventListener('click', (e) => {
            e.preventDefault();
            showFullWeather(cityName, lat, lon);
        });
        
        cityCell.appendChild(cityLink);
        
        // Add alert badge to city cell
        const alertSpan = document.createElement('span');
        alertSpan.id = `alert-badge-table-${index}`;
        alertSpan.style.marginLeft = '8px';

        // Render immediately from cache if available; otherwise fetch async.
        // Look up by ID at resolve time so the badge lands in the current DOM
        // even if renderCityList() rebuilt the table while the NWS request was in flight.
        const _tableCached = alertsCache[cityName];
        if (_tableCached && (Date.now() - _tableCached.timestamp < 600000)) {
            const badgeHTML = renderAlertBadge(_tableCached.alerts);
            if (badgeHTML) alertSpan.innerHTML = badgeHTML;
        } else {
            const _tableBadgeId = `alert-badge-table-${index}`;
            fetchWeatherAlerts(cityName, lat, lon).then(alerts => {
                const el = document.getElementById(_tableBadgeId);
                if (el) {
                    const badgeHTML = renderAlertBadge(alerts);
                    if (badgeHTML) el.innerHTML = badgeHTML;
                }
            });
        }
        cityCell.appendChild(alertSpan);
        
        row.appendChild(cityCell);
        
        if (weather && weather.current) {
            const current = weather.current;
            
            // Add cells based on config order
            currentConfig.cityListOrder.forEach(key => {
                if (!currentConfig.cityList[key]) return;
                
                const cell = document.createElement('td');
                
                switch(key) {
                    case 'temperature':
                        cell.textContent = `${convertTemperature(current.temperature_2m)}°${currentConfig.units.temperature}`;
                        break;
                    case 'conditions':
                        cell.textContent = WEATHER_CODES[current.weather_code] || 'Unknown';
                        break;
                    case 'feels_like':
                        cell.textContent = `${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}`;
                        break;
                    case 'humidity':
                        cell.textContent = `${current.relative_humidity_2m}%`;
                        break;
                    case 'wind_speed':
                        const windSpeed = convertWindSpeed(current.wind_speed_10m);
                        cell.textContent = `${windSpeed} ${currentConfig.units.wind_speed}`;
                        break;
                    case 'wind_gusts':
                        if (current.wind_gusts_10m) {
                            const gusts = convertWindSpeed(current.wind_gusts_10m);
                            cell.textContent = `${gusts} ${currentConfig.units.wind_speed}`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'wind_direction':
                        const windDir = degreesToCardinal(current.wind_direction_10m);
                        cell.textContent = `${windDir} (${current.wind_direction_10m}°)`;
                        break;
                    case 'uv_index':
                        if (current.uv_index !== null && current.uv_index !== undefined) {
                            const { category } = getUVIndexCategory(current.uv_index);
                            cell.textContent = `${Math.round(current.uv_index)} (${category})`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'high_temp':
                        if (weather.daily && weather.daily.temperature_2m_max) {
                            cell.textContent = `${convertTemperature(weather.daily.temperature_2m_max[0])}°${currentConfig.units.temperature}`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'low_temp':
                        if (weather.daily && weather.daily.temperature_2m_min) {
                            cell.textContent = `${convertTemperature(weather.daily.temperature_2m_min[0])}°${currentConfig.units.temperature}`;
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'sunrise':
                        if (weather.daily && weather.daily.sunrise && weather.daily.sunrise[0]) {
                            const sunriseTime = new Date(weather.daily.sunrise[0]);
                            cell.textContent = sunriseTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                    case 'sunset':
                        if (weather.daily && weather.daily.sunset && weather.daily.sunset[0]) {
                            const sunsetTime = new Date(weather.daily.sunset[0]);
                            cell.textContent = sunsetTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        } else {
                            cell.textContent = '-';
                        }
                        break;
                }
                
                row.appendChild(cell);
            });
        } else {
            // Loading cells - count enabled columns
            const enabledColumns = currentConfig.cityListOrder.filter(key => currentConfig.cityList[key]).length;
            for (let i = 0; i < enabledColumns; i++) {
                const loadingCell = document.createElement('td');
                loadingCell.textContent = 'Loading...';
                row.appendChild(loadingCell);
            }
        }
        
        // Actions cell
        const actionsCell = document.createElement('td');
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'table-actions';
        
        // Feature buttons with icons
        const historyBtn = createButton('📊', () => showHistoricalWeather(cityName, lat, lon));
        historyBtn.className = 'icon-btn-small feature-btn-small';
        historyBtn.setAttribute('aria-label', `View historical weather for ${cityName}`);
        historyBtn.title = 'Historical Weather';
        actionsDiv.appendChild(historyBtn);
        
        const precipBtn = createButton('💧', () => showPrecipitationNowcast(cityName, lat, lon));
        precipBtn.className = 'icon-btn-small feature-btn-small';
        precipBtn.setAttribute('aria-label', `View precipitation forecast for ${cityName}`);
        precipBtn.title = 'Expected Precipitation';
        actionsDiv.appendChild(precipBtn);
        
        const aroundBtn = createButton('🧭', () => showWeatherAroundMe(cityName, lat, lon));
        aroundBtn.className = 'icon-btn-small feature-btn-small';
        aroundBtn.setAttribute('aria-label', `View weather around ${cityName}`);
        aroundBtn.title = 'Weather Around Me';
        actionsDiv.appendChild(aroundBtn);
        
        // Movement buttons
        if (index > 0) {
            const upBtn = createButton('↑', `Move ${cityName} up`, () => moveCityUp(cityName));
            upBtn.className = 'icon-btn-small';
            actionsDiv.appendChild(upBtn);
        }
        
        if (index < Object.keys(cities).length - 1) {
            const downBtn = createButton('↓', `Move ${cityName} down`, () => moveCityDown(cityName));
            downBtn.className = 'icon-btn-small';
            actionsDiv.appendChild(downBtn);
        }
        
        const removeBtn = createButton('🗑️', `Remove ${cityName}`, () => removeCity(cityName));
        removeBtn.className = 'icon-btn-small remove-btn';
        actionsDiv.appendChild(removeBtn);
        
        actionsCell.appendChild(actionsDiv);
        row.appendChild(actionsCell);
        
        tbody.appendChild(row);
    });
    
    table.appendChild(tbody);
    
    // Wrap table in scrollable container to preserve table semantics
    const wrapper = document.createElement('div');
    wrapper.className = 'table-wrapper';
    wrapper.appendChild(table);
    container.appendChild(wrapper);
}

// Shared ARIA listbox setup helper
function setupListboxARIA(container, idPrefix) {
    container.setAttribute('role', 'listbox');
    container.setAttribute('tabindex', '0');
    container.removeAttribute('aria-label');
}

// Shared listbox item creator
function createListboxItem(index, idPrefix, text, ariaLabel) {
    const item = document.createElement('div');
    item.className = 'list-view-item';
    item.setAttribute('role', 'option');
    item.id = `${idPrefix}-${index}`;
    item.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    item.setAttribute('aria-label', ariaLabel || text);
    return item;
}

// Shared listbox keyboard navigation
function addListboxNavigation(container, idPrefix, onNavigate) {
    const navHandler = (e) => {
        const listItems = container.querySelectorAll(`[id^="${idPrefix}-"]`);
        const currentActive = container.getAttribute('aria-activedescendant');
        let activeIndex = 0;
        
        if (currentActive) {
            const parts = currentActive.split('-');
            activeIndex = parseInt(parts[parts.length - 1]);
        }
        
        let handled = false;
        let newIndex = activeIndex;
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (activeIndex < listItems.length - 1) {
                    newIndex = activeIndex + 1;
                }
                handled = true;
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (activeIndex > 0) {
                    newIndex = activeIndex - 1;
                }
                handled = true;
                break;
                
            case 'Home':
                e.preventDefault();
                newIndex = 0;
                handled = true;
                break;
                
            case 'End':
                e.preventDefault();
                newIndex = listItems.length - 1;
                handled = true;
                break;
                
            case 'Enter':
            case ' ':
                e.preventDefault();
                if (onNavigate && onNavigate.onActivate) {
                    onNavigate.onActivate(activeIndex, listItems[activeIndex]);
                }
                handled = true;
                break;
        }
        
        if (handled && newIndex !== activeIndex) {
            // Update aria-selected
            listItems.forEach((item, i) => {
                item.setAttribute('aria-selected', i === newIndex ? 'true' : 'false');
            });
            
            // Update aria-activedescendant
            container.setAttribute('aria-activedescendant', `${idPrefix}-${newIndex}`);
            
            // Scroll into view
            listItems[newIndex].scrollIntoView({ block: 'nearest' });
            
            // Call navigation callback
            if (onNavigate && onNavigate.onChange) {
                onNavigate.onChange(newIndex, listItems[newIndex]);
            }
            
            // Announce to screen reader
            if (listItems[newIndex]) {
                announceToScreenReader(listItems[newIndex].textContent);
            }
        }
    };
    
    // Remove old handler if exists
    if (container._listboxNavHandler) {
        container.removeEventListener('keydown', container._listboxNavHandler);
    }
    
    container._listboxNavHandler = navHandler;
    container.addEventListener('keydown', navHandler);
    return navHandler;
}

// List view (compact, keyboard navigable)
function renderListView(container) {
    setupListboxARIA(container, 'list-item');
    
    let activeIndex = 0;
    const cityNames = Object.keys(cities);
    const isCondensed = currentConfig.listViewStyle === 'condensed';
    
    // Create list items
    cityNames.forEach(async (cityName, index) => {
        const [lat, lon] = cities[cityName];
        const weather = weatherData[cityName];
        
        const item = document.createElement('div');
        item.className = 'list-view-item';
        item.setAttribute('role', 'option');
        item.id = `list-item-${index}`;
        item.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
        
        // City name - we'll add alert button separately
        let weatherText = cityName;
        let alertInfo = null;
        
        // Check for alerts
        try {
            const alerts = await fetchWeatherAlerts(cityName, lat, lon);
            if (alerts && alerts.length > 0) {
                const severityOrder = { extreme: 0, severe: 1, moderate: 2, minor: 3, unknown: 4 };
                const highestAlert = alerts.sort((a, b) => 
                    (severityOrder[a.severity] || 4) - (severityOrder[b.severity] || 4)
                )[0];
                
                if (alerts.length === 1) {
                    alertInfo = { text: `Alert: ${highestAlert.event}`, alert: highestAlert };
                } else {
                    alertInfo = { text: `Alerts: ${highestAlert.event} and ${alerts.length - 1} more`, alert: highestAlert };
                }
            }
        } catch (error) {
            // Silently continue without alerts if fetch fails
        }
        
        if (weather && weather.current) {
            const current = weather.current;
            const parts = [];
            
            // Add data in custom order
            currentConfig.cityListOrder.forEach(key => {
                if (!currentConfig.cityList[key]) return;
                
                switch(key) {
                    case 'temperature':
                        const temp = convertTemperature(current.temperature_2m);
                        parts.push(isCondensed ? 
                            `${temp}°${currentConfig.units.temperature}` : 
                            `Temperature: ${temp}°${currentConfig.units.temperature}`);
                        break;
                    case 'conditions':
                        const weatherDesc = WEATHER_CODES[current.weather_code] || 'Unknown';
                        parts.push(isCondensed ? weatherDesc : `Conditions: ${weatherDesc}`);
                        break;
                    case 'feels_like':
                        const feels = convertTemperature(current.apparent_temperature);
                        parts.push(isCondensed ? 
                            `${feels}°${currentConfig.units.temperature}` : 
                            `Feels Like: ${feels}°${currentConfig.units.temperature}`);
                        break;
                    case 'humidity':
                        parts.push(isCondensed ? 
                            `${current.relative_humidity_2m}%` : 
                            `Humidity: ${current.relative_humidity_2m}%`);
                        break;
                    case 'wind_speed':
                        const windSpeed = convertWindSpeed(current.wind_speed_10m);
                        parts.push(isCondensed ? 
                            `${windSpeed} ${currentConfig.units.wind_speed}` : 
                            `Wind: ${windSpeed} ${currentConfig.units.wind_speed}`);
                        break;
                    case 'wind_direction':
                        const windDir = degreesToCardinal(current.wind_direction_10m);
                        parts.push(isCondensed ? windDir : `Wind Direction: ${windDir}`);
                        break;
                    case 'wind_gusts':
                        if (current.wind_gusts_10m) {
                            const gusts = convertWindSpeed(current.wind_gusts_10m);
                            parts.push(isCondensed ? 
                                `gusts ${gusts} ${currentConfig.units.wind_speed}` : 
                                `Wind Gusts: ${gusts} ${currentConfig.units.wind_speed}`);
                        }
                        break;
                    case 'uv_index':
                        if (current.uv_index !== null && current.uv_index !== undefined) {
                            const { category } = getUVIndexCategory(current.uv_index);
                            parts.push(isCondensed ? 
                                `UV${Math.round(current.uv_index)}` : 
                                `UV: ${Math.round(current.uv_index)} (${category})`);
                        }
                        break;
                    case 'high_temp':
                        if (weather.daily) {
                            const high = convertTemperature(weather.daily.temperature_2m_max[0]);
                            parts.push(isCondensed ? 
                                `${high}°${currentConfig.units.temperature}` : 
                                `High: ${high}°${currentConfig.units.temperature}`);
                        }
                        break;
                    case 'low_temp':
                        if (weather.daily) {
                            const low = convertTemperature(weather.daily.temperature_2m_min[0]);
                            parts.push(isCondensed ? 
                                `${low}°${currentConfig.units.temperature}` : 
                                `Low: ${low}°${currentConfig.units.temperature}`);
                        }
                        break;
                    case 'sunrise':
                        if (weather.daily && weather.daily.sunrise && weather.daily.sunrise[0]) {
                            const sunriseTime = new Date(weather.daily.sunrise[0]);
                            const timeStr = sunriseTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                            parts.push(isCondensed ? timeStr : `Sunrise: ${timeStr}`);
                        }
                        break;
                    case 'sunset':
                        if (weather.daily && weather.daily.sunset && weather.daily.sunset[0]) {
                            const sunsetTime = new Date(weather.daily.sunset[0]);
                            const timeStr = sunsetTime.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                            parts.push(isCondensed ? timeStr : `Sunset: ${timeStr}`);
                        }
                        break;
                }
            });
            
            // Add alert info right after city name if present
            if (alertInfo) {
                weatherText = `${weatherText} (${alertInfo.text})`;
            }
            
            weatherText = `${weatherText} - ${parts.join(', ')}`;
        } else {
            // Add alert info right after city name if present
            if (alertInfo) {
                weatherText = `${weatherText} (${alertInfo.text})`;
            }
            weatherText = `${weatherText} - Loading...`;
        }
        
        // Create text node for main content
        const textNode = document.createTextNode(weatherText);
        item.appendChild(textNode);
        
        item.dataset.cityName = cityName;
        item.dataset.lat = lat;
        item.dataset.lon = lon;
        item.dataset.index = index;
        
        container.appendChild(item);
    });
    
    // Set initial active descendant
    container.setAttribute('aria-activedescendant', 'list-item-0');
    
    // Keyboard navigation handler
    listNavigationHandler = (e) => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        activeIndex = parseInt(currentActive.split('-')[2]);
        
        let handled = false;
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (activeIndex < items.length - 1) {
                    activeIndex++;
                    setActiveListItem(container, items, activeIndex);
                }
                handled = true;
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (activeIndex > 0) {
                    activeIndex--;
                    setActiveListItem(container, items, activeIndex);
                }
                handled = true;
                break;
                
            case 'Home':
                e.preventDefault();
                activeIndex = 0;
                setActiveListItem(container, items, activeIndex);
                handled = true;
                break;
                
            case 'End':
                e.preventDefault();
                activeIndex = items.length - 1;
                setActiveListItem(container, items, activeIndex);
                handled = true;
                break;
                
            case 'Enter':
            case ' ':
                e.preventDefault();
                const activeItem = items[activeIndex];
                const cityName = activeItem.dataset.cityName;
                const lat = parseFloat(activeItem.dataset.lat);
                const lon = parseFloat(activeItem.dataset.lon);
                showFullWeather(cityName, lat, lon);
                handled = true;
                break;
        }
    };
    
    // Function to update button labels and alert badge based on current selection
    const updateButtonLabels = async (index) => {
        const items = container.querySelectorAll('.list-view-item');
        if (items[index]) {
            const cityName = items[index].dataset.cityName;
            const lat = parseFloat(items[index].dataset.lat);
            const lon = parseFloat(items[index].dataset.lon);
            
            upBtn.textContent = `↑ Move ${cityName} Up`;
            historyBtn.textContent = `📊 ${cityName} History`;
            precipBtn.textContent = `💧 ${cityName} Precipitation`;
            aroundBtn.textContent = `🧭 Around ${cityName}`;
            alertBtn.textContent = `⚠️ ${cityName} Alerts`;
            downBtn.textContent = `↓ Move ${cityName} Down`;
            removeBtn.textContent = `🗑️ Remove ${cityName}`;
            detailsBtn.textContent = `📋 ${cityName} Details`;
            
            // Update alert badge for selected city
            try {
                const alerts = await fetchWeatherAlerts(cityName, lat, lon);
                const alertBadge = renderAlertBadge(alerts, cityName, lat, lon);
                alertSpan.innerHTML = alertBadge; // renderAlertBadge returns HTML string, not DOM element
            } catch (error) {
                console.error('Error loading alerts for list view:', error);
                alertSpan.innerHTML = '';
            }
        }
    };
    
    // Wrap the existing navigation handler to update button labels
    const originalHandler = listNavigationHandler;
    listNavigationHandler = (e) => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const oldIndex = parseInt(currentActive.split('-')[2]);
        
        // Call original handler
        originalHandler(e);
        
        // Check if index changed
        const newActive = container.getAttribute('aria-activedescendant');
        const newIndex = parseInt(newActive.split('-')[2]);
        
        if (newIndex !== oldIndex) {
            updateButtonLabels(newIndex);
            // Announce after button labels update to avoid conflicts
            if (items[newIndex]) {
                announceToScreenReader(items[newIndex].textContent);
            }
        }
    };
    
    // Remove old handler if exists (prevent memory leak)
    if (container._cityListNavHandler) {
        container.removeEventListener('keydown', container._cityListNavHandler);
    }
    
    container._cityListNavHandler = listNavigationHandler;
    container.addEventListener('keydown', listNavigationHandler);
    
    // Add control buttons for list view (single set that acts on focused city)
    const controlsDiv = document.createElement('div');
    controlsDiv.className = 'list-view-controls';
    
    // Feature buttons
    const historyBtn = createButton('📊 History', 'View historical weather for selected city', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        const lat = parseFloat(items[activeIndex].dataset.lat);
        const lon = parseFloat(items[activeIndex].dataset.lon);
        showHistoricalWeather(cityName, lat, lon);
    });
    historyBtn.className = 'list-control-btn feature-btn';
    
    const precipBtn = createButton('💧 Precipitation', 'View precipitation forecast for selected city', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        const lat = parseFloat(items[activeIndex].dataset.lat);
        const lon = parseFloat(items[activeIndex].dataset.lon);
        showPrecipitationNowcast(cityName, lat, lon);
    });
    precipBtn.className = 'list-control-btn feature-btn';
    
    const aroundBtn = createButton('🧭 Around Me', 'View weather around selected city', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        const lat = parseFloat(items[activeIndex].dataset.lat);
        const lon = parseFloat(items[activeIndex].dataset.lon);
        showWeatherAroundMe(cityName, lat, lon);
    });
    aroundBtn.className = 'list-control-btn feature-btn';
    
    const alertBtn = createButton('⚠️ Alerts', 'View weather alerts for selected city', async () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        const lat = parseFloat(items[activeIndex].dataset.lat);
        const lon = parseFloat(items[activeIndex].dataset.lon);
        
        try {
            const alerts = await fetchWeatherAlerts(cityName, lat, lon);
            if (alerts && alerts.length > 0) {
                showAlertDetails(alerts[0]);
            }
            // If no alerts, do nothing - absence doesn't need announcement
        } catch (error) {
            announceToScreenReader(`Error loading alerts for ${cityName}`);
        }
    });
    alertBtn.className = 'list-control-btn feature-btn';
    alertBtn.id = 'list-alert-btn';
    
    // Alert badge for selected city (visual indicator)
    const alertSpan = document.createElement('span');
    alertSpan.id = 'list-view-alert-badge';
    alertSpan.className = 'alert-container';
    
    // Movement and action buttons
    const upBtn = createButton('↑ Move Up', 'Move selected city up in list', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        moveCityUp(cityName);
    });
    upBtn.className = 'list-control-btn';
    
    const downBtn = createButton('↓ Move Down', 'Move selected city down in list', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        moveCityDown(cityName);
    });
    downBtn.className = 'list-control-btn';
    
    const removeBtn = createButton('🗑️ Remove', 'Remove selected city from list', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        removeCity(cityName);
    });
    removeBtn.className = 'list-control-btn remove-btn';
    
    const detailsBtn = createButton('📋 Full Details', 'View full weather details for selected city', () => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        const activeIndex = parseInt(currentActive.split('-')[2]);
        const cityName = items[activeIndex].dataset.cityName;
        const lat = parseFloat(items[activeIndex].dataset.lat);
        const lon = parseFloat(items[activeIndex].dataset.lon);
        showFullWeather(cityName, lat, lon);
    });
    detailsBtn.className = 'list-control-btn';
    
    controlsDiv.appendChild(detailsBtn);
    controlsDiv.appendChild(historyBtn);
    controlsDiv.appendChild(precipBtn);
    controlsDiv.appendChild(aroundBtn);
    controlsDiv.appendChild(alertBtn);
    controlsDiv.appendChild(alertSpan);
    controlsDiv.appendChild(upBtn);
    controlsDiv.appendChild(downBtn);
    controlsDiv.appendChild(removeBtn);
    
    container.parentElement.insertBefore(controlsDiv, container.nextSibling);
    
    // Set initial button labels
    updateButtonLabels(0);
}

function setActiveListItem(container, items, index) {
    // Update aria-selected
    items.forEach((item, i) => {
        item.setAttribute('aria-selected', i === index ? 'true' : 'false');
    });
    
    // Update aria-activedescendant
    container.setAttribute('aria-activedescendant', `list-item-${index}`);
    
    // Scroll into view
    items[index].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

// City management
function moveCityUp(cityName) {
    const keys = Object.keys(cities);
    const index = keys.indexOf(cityName);
    if (index <= 0) return;
    
    const newCities = {};
    keys.forEach((key, i) => {
        if (i === index - 1) {
            newCities[cityName] = cities[cityName];
        } else if (i === index) {
            newCities[keys[index - 1]] = cities[keys[index - 1]];
        } else {
            newCities[key] = cities[key];
        }
    });
    
    cities = newCities;
    saveCitiesToStorage();
    renderCityList();
    announceToScreenReader(`Moved ${cityName} up in the list`);
}

function moveCityDown(cityName) {
    const keys = Object.keys(cities);
    const index = keys.indexOf(cityName);
    if (index < 0 || index >= keys.length - 1) return;
    
    const newCities = {};
    keys.forEach((key, i) => {
        if (i === index) {
            newCities[keys[index + 1]] = cities[keys[index + 1]];
        } else if (i === index + 1) {
            newCities[cityName] = cities[cityName];
        } else {
            newCities[key] = cities[key];
        }
    });
    
    cities = newCities;
    saveCitiesToStorage();
    renderCityList();
    announceToScreenReader(`Moved ${cityName} down in the list`);
}

async function refreshCity(cityName, lat, lon) {
    announceToScreenReader(`Refreshing weather for ${cityName}`);
    try {
        await fetchWeatherForCity(cityName, lat, lon);
    } catch (error) {
        console.error('Failed to refresh city:', error);
        announceToScreenReader(`Failed to refresh ${cityName}`);
    }
}

async function refreshAllCities() {
    if (Object.keys(cities).length === 0) return;
    
    announceToScreenReader('Refreshing all cities');
    
    const promises = Object.entries(cities).map(([cityName, [lat, lon]]) => 
        fetchWeatherForCity(cityName, lat, lon, false, true) // silent = true, we announce at start/end
    );
    
    try {
        await Promise.all(promises);
        announceToScreenReader('All cities refreshed');
    } catch (error) {
        announceToScreenReader('Some cities failed to refresh');
    }
}

function removeCity(cityName) {
    if (!confirm(`Remove ${cityName} from your cities?`)) return;
    
    delete cities[cityName];
    delete weatherData[cityName];
    saveCitiesToStorage();
    renderCityList();
    announceToScreenReader(`Removed ${cityName} from your cities`);
}

// Full weather details
async function showFullWeather(cityName, lat, lon) {
    const dialog = document.getElementById('weather-details-dialog');
    const title = document.getElementById('weather-details-title');
    const content = document.getElementById('weather-details-content');
    
    title.textContent = `Full Weather Details - ${cityName}`;
    content.innerHTML = '<p class="loading-text">Loading detailed forecast...</p>';
    
    closeAllModals();
    focusReturnElement = document.activeElement;
    dialog.hidden = false;
    trapFocus(dialog);
    
    try {
        const weather = await fetchWeatherForCity(cityName, lat, lon, true);
        content.innerHTML = renderFullWeatherDetails(weather);
        
        // Setup keyboard navigation for list views if they exist
        // Setup keyboard navigation for list views if they exist
        const currentList = document.getElementById('current-conditions-list');
        if (currentList) {
            addListboxNavigation(currentList, 'current-item', {});
            currentList.setAttribute('aria-activedescendant', 'current-item-0');
            currentList.style.outline = '2px solid var(--focus-outline)';
            currentList.addEventListener('focus', () => {
                currentList.style.outline = '2px solid var(--focus-outline)';
            });
            currentList.addEventListener('blur', () => {
                currentList.style.outline = '2px solid transparent';
            });
            // Set focus to current conditions list if it exists
            currentList.focus();
        }
        
        const hourlyList = document.getElementById('hourly-forecast-list');
        if (hourlyList) {
            addListboxNavigation(hourlyList, 'hourly-item', {});
            hourlyList.setAttribute('aria-activedescendant', 'hourly-item-0');
            hourlyList.style.outline = '2px solid var(--focus-outline)';
            hourlyList.addEventListener('focus', () => {
                hourlyList.style.outline = '2px solid var(--focus-outline)';
            });
            hourlyList.addEventListener('blur', () => {
                hourlyList.style.outline = '2px solid transparent';
            });
        }
        
        const dailyList = document.getElementById('daily-forecast-list');
        if (dailyList) {
            addListboxNavigation(dailyList, 'daily-item', {});
            dailyList.setAttribute('aria-activedescendant', 'daily-item-0');
            dailyList.style.outline = '2px solid var(--focus-outline)';
            dailyList.addEventListener('focus', () => {
                dailyList.style.outline = '2px solid var(--focus-outline)';
            });
            dailyList.addEventListener('blur', () => {
                dailyList.style.outline = '2px solid transparent';
            });
        }
    } catch (error) {
        content.innerHTML = `<p class="error-message">Failed to load detailed forecast: ${error.message}</p>`;
    }
}

function renderCurrentConditions(weather) {
    const current = weather.current;
    const viewMode = currentConfig.currentConditionsView || 'flat';
    let html = '<section><h4>Current Conditions</h4>';
    
    if (viewMode === 'table') {
        html += '<div class="table-container"><table class="weather-table"><thead><tr>';
        html += '<th scope="col">Field</th><th scope="col">Value</th>';
        html += '</tr></thead><tbody>';
        
        html += `<tr><th scope="row">Temperature</th><td>${convertTemperature(current.temperature_2m)}°${currentConfig.units.temperature}</td></tr>`;
        html += `<tr><th scope="row">Feels Like</th><td>${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}</td></tr>`;
        html += `<tr><th scope="row">Weather</th><td>${WEATHER_CODES[current.weather_code] || 'Unknown'}</td></tr>`;
        html += `<tr><th scope="row">Humidity</th><td>${current.relative_humidity_2m}%</td></tr>`;
        
        const windCardinal = degreesToCardinal(current.wind_direction_10m);
        let windText = `${convertWindSpeed(current.wind_speed_10m)} ${currentConfig.units.wind_speed} ${windCardinal} (${current.wind_direction_10m}°)`;
        if (currentConfig.current.wind_gusts && current.wind_gusts_10m) {
            windText += `, gusts to ${convertWindSpeed(current.wind_gusts_10m)} ${currentConfig.units.wind_speed}`;
        }
        html += `<tr><th scope="row">Wind</th><td>${windText}</td></tr>`;
        
        if (currentConfig.current.uv_index && current.uv_index !== null && current.uv_index !== undefined) {
            html += `<tr><th scope="row">UV Index</th><td>${getUVIndexDescription(current.uv_index)}</td></tr>`;
        }
        
        if (currentConfig.current.dew_point && current.dewpoint_2m !== null && current.dewpoint_2m !== undefined) {
            html += `<tr><th scope="row">Dew Point</th><td>${formatDewPoint(current.dewpoint_2m)}</td></tr>`;
        }
        
        html += `<tr><th scope="row">Pressure</th><td>${convertPressure(current.pressure_msl)} ${currentConfig.units.pressure}</td></tr>`;
        html += `<tr><th scope="row">Cloud Cover</th><td>${current.cloud_cover}%</td></tr>`;
        html += `<tr><th scope="row">Visibility</th><td>${convertDistance(current.visibility)} ${currentConfig.units.distance}</td></tr>`;
        
        html += '</tbody></table></div>';
    } else if (viewMode === 'list') {
        const isCondensed = currentConfig.listViewStyle === 'condensed';
        html += '<div role="listbox" tabindex="0" class="weather-list" id="current-conditions-list" style="list-style: none; padding: 0; outline: 2px solid transparent; transition: outline 0.2s;">';
        
        const fields = [
            { label: 'Temperature', value: `${convertTemperature(current.temperature_2m)}°${currentConfig.units.temperature}` },
            { label: 'Feels Like', value: `${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}` },
            { label: 'Weather', value: WEATHER_CODES[current.weather_code] || 'Unknown' },
            { label: 'Humidity', value: `${current.relative_humidity_2m}%` }
        ];
        
        const windCardinal = degreesToCardinal(current.wind_direction_10m);
        let windValue = `${convertWindSpeed(current.wind_speed_10m)} ${currentConfig.units.wind_speed} ${windCardinal}`;
        if (currentConfig.current.wind_gusts && current.wind_gusts_10m) {
            windValue += `, gusts ${convertWindSpeed(current.wind_gusts_10m)} ${currentConfig.units.wind_speed}`;
        }
        fields.push({ label: 'Wind', value: windValue });
        
        if (currentConfig.current.uv_index && current.uv_index !== null && current.uv_index !== undefined) {
            fields.push({ label: 'UV Index', value: getUVIndexDescription(current.uv_index) });
        }
        
        if (currentConfig.current.dew_point && current.dewpoint_2m !== null && current.dewpoint_2m !== undefined) {
            fields.push({ label: 'Dew Point', value: formatDewPoint(current.dewpoint_2m) });
        }
        
        fields.push({ label: 'Pressure', value: `${convertPressure(current.pressure_msl)} ${currentConfig.units.pressure}` });
        fields.push({ label: 'Cloud Cover', value: `${current.cloud_cover}%` });
        fields.push({ label: 'Visibility', value: `${convertDistance(current.visibility)} ${currentConfig.units.distance}` });
        
        fields.forEach((field, i) => {
            const visualText = isCondensed ? `${field.label}: ${field.value}` : `${field.label} • ${field.value}`;
            html += `<div role="option" id="current-item-${i}" aria-selected="${i === 0 ? 'true' : 'false'}" style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">${visualText}</div>`;
        });
        
        html += '</div>';
    } else {
        // Flat/Card view (default)
        html += '<dl>';
        html += `<dt>Temperature:</dt><dd>${convertTemperature(current.temperature_2m)}°${currentConfig.units.temperature}</dd>`;
        html += `<dt>Feels Like:</dt><dd>${convertTemperature(current.apparent_temperature)}°${currentConfig.units.temperature}</dd>`;
        html += `<dt>Weather:</dt><dd>${WEATHER_CODES[current.weather_code] || 'Unknown'}</dd>`;
        html += `<dt>Humidity:</dt><dd>${current.relative_humidity_2m}%</dd>`;
        
        const windCardinal = degreesToCardinal(current.wind_direction_10m);
        let windText = `${convertWindSpeed(current.wind_speed_10m)} ${currentConfig.units.wind_speed} ${windCardinal} (${current.wind_direction_10m}°)`;
        if (currentConfig.current.wind_gusts && current.wind_gusts_10m) {
            windText += `, gusts to ${convertWindSpeed(current.wind_gusts_10m)} ${currentConfig.units.wind_speed}`;
        }
        html += `<dt>Wind:</dt><dd>${windText}</dd>`;
        
        if (currentConfig.current.uv_index && current.uv_index !== null && current.uv_index !== undefined) {
            html += `<dt>UV Index:</dt><dd>${getUVIndexDescription(current.uv_index)}</dd>`;
        }
        
        if (currentConfig.current.dew_point && current.dewpoint_2m !== null && current.dewpoint_2m !== undefined) {
            html += `<dt>Dew Point:</dt><dd>${formatDewPoint(current.dewpoint_2m)}</dd>`;
        }
        
        html += `<dt>Pressure:</dt><dd>${convertPressure(current.pressure_msl)} ${currentConfig.units.pressure}</dd>`;
        html += `<dt>Cloud Cover:</dt><dd>${current.cloud_cover}%</dd>`;
        html += `<dt>Visibility:</dt><dd>${convertDistance(current.visibility)} ${currentConfig.units.distance}</dd>`;
        html += '</dl>';
    }
    
    html += '</section>';
    return html;
}

function renderFullWeatherDetails(weather) {
    let html = '<div class="full-weather-details">';
    
    // Current conditions with view mode support
    html += renderCurrentConditions(weather);
    
    // Next 24 hours hourly forecast
    if (weather.hourly) {
        html += '<section><h4>Next 24 Hours</h4>';
        html += renderHourlyForecast(weather);
        html += '</section>';
    }
    
    // 16-day forecast
    if (weather.daily) {
        html += '<section><h4>16-Day Forecast</h4>';
        html += renderDailyForecast(weather);
        html += '</section>';
    }
    
    html += '</div>';
    return html;
}

function renderHourlyForecast(weather) {
    const viewMode = currentConfig.hourlyDetailView || 'flat';
    let html = '';
    
    // Get current time and find the starting hour index
    const now = new Date();
    let startIndex = 0;
    for (let i = 0; i < weather.hourly.time.length; i++) {
        const hourTime = new Date(weather.hourly.time[i]);
        if (hourTime >= now) {
            startIndex = i;
            break;
        }
    }
    
    const endIndex = Math.min(startIndex + 24, weather.hourly.time.length);
    
    if (viewMode === 'table') {
        html += '<div style="overflow-x: auto;"><table class="weather-table">';
        html += '<thead><tr>';
        html += '<th scope="col">Time</th>';
        html += '<th scope="col">Conditions</th>';
        if (currentConfig.hourly.temperature) html += '<th scope="col">Temp</th>';
        if (currentConfig.hourly.feels_like) html += '<th scope="col">Feels Like</th>';
        if (currentConfig.hourly.humidity) html += '<th scope="col">Humidity</th>';
        if (currentConfig.hourly.precipitation) html += '<th scope="col">Precip</th>';
        if (currentConfig.hourly.precipitation_probability) html += '<th scope="col">Precip %</th>';
        if (currentConfig.hourly.uv_index) html += '<th scope="col">UV</th>';
        if (currentConfig.hourly.wind_speed) html += '<th scope="col">Wind</th>';
        if (currentConfig.hourly.dew_point) html += '<th scope="col">Dew Point</th>';
        if (currentConfig.hourly.cloud_cover) html += '<th scope="col">Clouds</th>';
        html += '</tr></thead><tbody>';
        
        for (let i = startIndex; i < endIndex; i++) {
            const hourTime = new Date(weather.hourly.time[i]);
            const timeStr = hourTime.toLocaleTimeString(undefined, { hour: 'numeric', hour12: true });
            
            html += '<tr>';
            html += `<th scope="row">${timeStr}</th>`;
            html += `<td>${WEATHER_CODES[weather.hourly.weathercode[i]] || 'Unknown'}</td>`;
            if (currentConfig.hourly.temperature) html += `<td>${convertTemperature(weather.hourly.temperature_2m[i])}°${currentConfig.units.temperature}</td>`;
            if (currentConfig.hourly.feels_like) html += `<td>${convertTemperature(weather.hourly.apparent_temperature[i])}°${currentConfig.units.temperature}</td>`;
            if (currentConfig.hourly.humidity) html += `<td>${weather.hourly.relative_humidity_2m[i]}%</td>`;
            if (currentConfig.hourly.precipitation) html += `<td>${convertPrecipitation(weather.hourly.precipitation[i])} ${currentConfig.units.precipitation}</td>`;
            if (currentConfig.hourly.precipitation_probability && weather.hourly.precipitation_probability) html += `<td>${weather.hourly.precipitation_probability[i]}%</td>`;
            if (currentConfig.hourly.uv_index && weather.hourly.uv_index && weather.hourly.uv_index[i] !== null) {
                const { category } = getUVIndexCategory(weather.hourly.uv_index[i]);
                html += `<td>${Math.round(weather.hourly.uv_index[i])} (${category})</td>`;
            } else if (currentConfig.hourly.uv_index) {
                html += '<td>-</td>';
            }
            if (currentConfig.hourly.wind_speed) {
                let windText = `${convertWindSpeed(weather.hourly.windspeed_10m[i])} ${currentConfig.units.wind_speed}`;
                if (currentConfig.hourly.wind_gusts && weather.hourly.windgusts_10m) {
                    windText += `, gusts ${convertWindSpeed(weather.hourly.windgusts_10m[i])}`;
                }
                html += `<td>${windText}</td>`;
            }
            if (currentConfig.hourly.dew_point && weather.hourly.dewpoint_2m) html += `<td>${formatDewPoint(weather.hourly.dewpoint_2m[i])}</td>`;
            if (currentConfig.hourly.cloud_cover) html += `<td>${weather.hourly.cloudcover[i]}%</td>`;
            html += '</tr>';
        }
        
        html += '</tbody></table></div>';
    } else if (viewMode === 'list') {
        // Listbox pattern for keyboard navigation
        html += '<div role="listbox" tabindex="0" class="weather-list" id="hourly-forecast-list" style="list-style: none; padding: 0; outline: 2px solid transparent; transition: outline 0.2s;">';
        
        const isCondensed = currentConfig.listViewStyle === 'condensed';
        
        for (let i = startIndex; i < endIndex; i++) {
            const hourTime = new Date(weather.hourly.time[i]);
            const timeStr = hourTime.toLocaleTimeString(undefined, { hour: 'numeric', hour12: true });
            
            // Build aria-label and visual text
            let ariaLabel = `${timeStr}, ${WEATHER_CODES[weather.hourly.weathercode[i]] || 'Unknown'}`;
            let visualText = `<strong>${timeStr}</strong> - ${WEATHER_CODES[weather.hourly.weathercode[i]] || 'Unknown'}`;
            
            let details = [];
            if (currentConfig.hourly.temperature) {
                const temp = `${convertTemperature(weather.hourly.temperature_2m[i])}°${currentConfig.units.temperature}`;
                details.push(isCondensed ? temp : `Temperature: ${temp}`);
            }
            if (currentConfig.hourly.feels_like) {
                const feels = `${convertTemperature(weather.hourly.apparent_temperature[i])}°${currentConfig.units.temperature}`;
                details.push(isCondensed ? `Feels ${feels}` : `Feels Like: ${feels}`);
            }
            if (currentConfig.hourly.humidity) {
                details.push(isCondensed ? `${weather.hourly.relative_humidity_2m[i]}%` : `Humidity: ${weather.hourly.relative_humidity_2m[i]}%`);
            }
            if (currentConfig.hourly.precipitation) {
                const precip = `${convertPrecipitation(weather.hourly.precipitation[i])} ${currentConfig.units.precipitation}`;
                details.push(isCondensed ? precip : `Precip: ${precip}`);
            }
            if (currentConfig.hourly.precipitation_probability && weather.hourly.precipitation_probability) {
                details.push(isCondensed ? `${weather.hourly.precipitation_probability[i]}%` : `Precip Chance: ${weather.hourly.precipitation_probability[i]}%`);
            }
            if (currentConfig.hourly.uv_index && weather.hourly.uv_index && weather.hourly.uv_index[i] !== null) {
                const { category } = getUVIndexCategory(weather.hourly.uv_index[i]);
                details.push(isCondensed ? `UV${Math.round(weather.hourly.uv_index[i])}` : `UV: ${Math.round(weather.hourly.uv_index[i])} (${category})`);
            }
            if (currentConfig.hourly.wind_speed) {
                let windText = `${convertWindSpeed(weather.hourly.windspeed_10m[i])} ${currentConfig.units.wind_speed}`;
                if (currentConfig.hourly.wind_gusts && weather.hourly.windgusts_10m) {
                    windText += `, gusts ${convertWindSpeed(weather.hourly.windgusts_10m[i])}`;
                }
                details.push(isCondensed ? windText : `Wind: ${windText}`);
            }
            if (currentConfig.hourly.dew_point && weather.hourly.dewpoint_2m) {
                const dp = formatDewPoint(weather.hourly.dewpoint_2m[i]);
                details.push(isCondensed ? dp : `Dew Point: ${dp}`);
            }
            if (currentConfig.hourly.cloud_cover) {
                details.push(isCondensed ? `${weather.hourly.cloudcover[i]}%` : `Cloud Cover: ${weather.hourly.cloudcover[i]}%`);
            }
            
            if (details.length > 0) {
                visualText += ` • ${details.join(' • ')}`;
                ariaLabel += `, ${details.join(', ')}`;
            }
            
            html += `<div role="option" id="hourly-item-${i}" aria-selected="${i === 0 ? 'true' : 'false'}" style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">${visualText}</div>`;
        }
        
        html += '</div>';
    } else {
        // Flat/Card view (default)
        html += '<ul class="hourly-forecast">';
        
        for (let i = startIndex; i < endIndex; i++) {
            const hourTime = new Date(weather.hourly.time[i]);
            const timeStr = hourTime.toLocaleTimeString(undefined, { hour: 'numeric', hour12: true });
            
            html += '<li class="hourly-item">';
            html += `<strong>${timeStr}</strong>`;
            html += `<p class="hourly-weather">${WEATHER_CODES[weather.hourly.weathercode[i]] || 'Unknown'}</p>`;
            if (currentConfig.hourly.temperature) html += `<p class="hourly-temp">${convertTemperature(weather.hourly.temperature_2m[i])}°${currentConfig.units.temperature}</p>`;
            
            if (currentConfig.hourly.feels_like) {
                html += `<p>Feels: ${convertTemperature(weather.hourly.apparent_temperature[i])}°${currentConfig.units.temperature}</p>`;
            }
            
            if (currentConfig.hourly.humidity) {
                html += `<p>Humidity: ${weather.hourly.relative_humidity_2m[i]}%</p>`;
            }
            
            if (currentConfig.hourly.precipitation) {
                html += `<p>Precip: ${convertPrecipitation(weather.hourly.precipitation[i])} ${currentConfig.units.precipitation}</p>`;
            }
            
            if (currentConfig.hourly.precipitation_probability && weather.hourly.precipitation_probability) {
                html += `<p>Precip Chance: ${weather.hourly.precipitation_probability[i]}%</p>`;
            }
            
            if (currentConfig.hourly.uv_index && weather.hourly.uv_index && weather.hourly.uv_index[i] !== null) {
                const { category } = getUVIndexCategory(weather.hourly.uv_index[i]);
                html += `<p>UV: ${Math.round(weather.hourly.uv_index[i])} (${category})</p>`;
            }
            
            if (currentConfig.hourly.wind_speed) {
                let windText = `${convertWindSpeed(weather.hourly.windspeed_10m[i])} ${currentConfig.units.wind_speed}`;
                if (currentConfig.hourly.wind_gusts && weather.hourly.windgusts_10m) {
                    windText += `, gusts ${convertWindSpeed(weather.hourly.windgusts_10m[i])} ${currentConfig.units.wind_speed}`;
                }
                html += `<p>Wind: ${windText}</p>`;
            }
            
            if (currentConfig.hourly.dew_point && weather.hourly.dewpoint_2m) {
                html += `<p>Dew Point: ${formatDewPoint(weather.hourly.dewpoint_2m[i])}</p>`;
            }
            
            if (currentConfig.hourly.cloud_cover) {
                html += `<p>Clouds: ${weather.hourly.cloudcover[i]}%</p>`;
            }
            
            html += '</li>';
        }
        
        html += '</ul>';
    }
    
    return html;
}

function renderDailyForecast(weather) {
    const viewMode = currentConfig.dailyDetailView || 'flat';
    let html = '';
    
    if (viewMode === 'table') {
        html += '<div style="overflow-x: auto;"><table class="weather-table">';
        html += '<thead><tr>';
        html += '<th scope="col">Day</th>';
        html += '<th scope="col">Conditions</th>';
        if (currentConfig.daily.temperature_max) html += '<th scope="col">High</th>';
        if (currentConfig.daily.temperature_min) html += '<th scope="col">Low</th>';
        if (currentConfig.daily.precipitation_sum) html += '<th scope="col">Precip</th>';
        if (currentConfig.daily.precipitation_probability) html += '<th scope="col">Precip %</th>';
        if (currentConfig.daily.uv_index_max) html += '<th scope="col">UV</th>';
        if (currentConfig.daily.sunrise) html += '<th scope="col">Sunrise</th>';
        if (currentConfig.daily.sunset) html += '<th scope="col">Sunset</th>';
        if (currentConfig.daily.daylight_duration) html += '<th scope="col">Daylight</th>';
        if (currentConfig.daily.sunshine_duration) html += '<th scope="col">Sunshine</th>';
        if (currentConfig.daily.wind_speed_max) html += '<th scope="col">Max Wind</th>';
        html += '</tr></thead><tbody>';
        
        for (let i = 0; i < 16 && i < weather.daily.time.length; i++) {
            const date = new Date(weather.daily.time[i]);
            let dayLabel;
            if (i === 0) {
                dayLabel = 'Today';
            } else {
                const weekday = date.toLocaleDateString(undefined, { weekday: 'short' });
                const monthDay = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                dayLabel = `${weekday}, ${monthDay}`;
            }
            
            html += '<tr>';
            html += `<th scope="row">${dayLabel}</th>`;
            html += `<td>${WEATHER_CODES[weather.daily.weathercode[i]] || 'Unknown'}</td>`;
            if (currentConfig.daily.temperature_max) html += `<td>${convertTemperature(weather.daily.temperature_2m_max[i])}°${currentConfig.units.temperature}</td>`;
            if (currentConfig.daily.temperature_min) html += `<td>${convertTemperature(weather.daily.temperature_2m_min[i])}°${currentConfig.units.temperature}</td>`;
            if (currentConfig.daily.precipitation_sum) html += `<td>${convertPrecipitation(weather.daily.precipitation_sum[i])} ${currentConfig.units.precipitation}</td>`;
            if (currentConfig.daily.precipitation_probability && weather.daily.precipitation_probability_max) html += `<td>${weather.daily.precipitation_probability_max[i]}%</td>`;
            if (currentConfig.daily.uv_index_max && weather.daily.uv_index_max && weather.daily.uv_index_max[i] !== null) {
                const { category } = getUVIndexCategory(weather.daily.uv_index_max[i]);
                html += `<td>${Math.round(weather.daily.uv_index_max[i])} (${category})</td>`;
            } else if (currentConfig.daily.uv_index_max) {
                html += '<td>-</td>';
            }
            if (currentConfig.daily.sunrise && weather.daily.sunrise) {
                const sunrise = new Date(weather.daily.sunrise[i]).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                html += `<td>${sunrise}</td>`;
            }
            if (currentConfig.daily.sunset && weather.daily.sunset) {
                const sunset = new Date(weather.daily.sunset[i]).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                html += `<td>${sunset}</td>`;
            }
            if (currentConfig.daily.daylight_duration && weather.daily.daylight_duration) html += `<td>${formatDuration(weather.daily.daylight_duration[i])}</td>`;
            if (currentConfig.daily.sunshine_duration && weather.daily.sunshine_duration) html += `<td>${formatDuration(weather.daily.sunshine_duration[i])}</td>`;
            if (currentConfig.daily.wind_speed_max && weather.daily.windspeed_10m_max) html += `<td>${convertWindSpeed(weather.daily.windspeed_10m_max[i])} ${currentConfig.units.wind_speed}</td>`;
            html += '</tr>';
        }
        
        html += '</tbody></table></div>';
    } else if (viewMode === 'list') {
        // Listbox pattern for keyboard navigation
        html += '<div role="listbox" tabindex="0" class="weather-list" id="daily-forecast-list" style="list-style: none; padding: 0; outline: 2px solid transparent; transition: outline 0.2s;">';
        
        const isCondensed = currentConfig.listViewStyle === 'condensed';
        
        for (let i = 0; i < 16 && i < weather.daily.time.length; i++) {
            const date = new Date(weather.daily.time[i]);
            let dayLabel;
            if (i === 0) {
                dayLabel = 'Today';
            } else {
                const weekday = date.toLocaleDateString(undefined, { weekday: 'short' });
                const monthDay = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                dayLabel = `${weekday}, ${monthDay}`;
            }
            
            // Build visual text (no aria-label, no <strong> tags - following hourly pattern)
            let visualText = `${dayLabel} - ${WEATHER_CODES[weather.daily.weathercode[i]] || 'Unknown'}`;
            
            let details = [];
            if (currentConfig.daily.temperature_max && currentConfig.daily.temperature_min) {
                const temps = `${convertTemperature(weather.daily.temperature_2m_max[i])}°/${convertTemperature(weather.daily.temperature_2m_min[i])}°${currentConfig.units.temperature}`;
                details.push(isCondensed ? temps : `High/Low: ${temps}`);
            } else if (currentConfig.daily.temperature_max) {
                const high = `${convertTemperature(weather.daily.temperature_2m_max[i])}°${currentConfig.units.temperature}`;
                details.push(isCondensed ? high : `High: ${high}`);
            } else if (currentConfig.daily.temperature_min) {
                const low = `${convertTemperature(weather.daily.temperature_2m_min[i])}°${currentConfig.units.temperature}`;
                details.push(isCondensed ? low : `Low: ${low}`);
            }
            if (currentConfig.daily.precipitation_sum) {
                const precip = `${convertPrecipitation(weather.daily.precipitation_sum[i])} ${currentConfig.units.precipitation}`;
                details.push(isCondensed ? precip : `Precip: ${precip}`);
            }
            if (currentConfig.daily.precipitation_probability && weather.daily.precipitation_probability_max) {
                details.push(isCondensed ? `${weather.daily.precipitation_probability_max[i]}%` : `Precip Chance: ${weather.daily.precipitation_probability_max[i]}%`);
            }
            if (currentConfig.daily.uv_index_max && weather.daily.uv_index_max && weather.daily.uv_index_max[i] !== null) {
                const { category } = getUVIndexCategory(weather.daily.uv_index_max[i]);
                details.push(isCondensed ? `UV${Math.round(weather.daily.uv_index_max[i])}` : `UV: ${Math.round(weather.daily.uv_index_max[i])} (${category})`);
            }
            if (currentConfig.daily.sunrise && weather.daily.sunrise) {
                const sunrise = new Date(weather.daily.sunrise[i]).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                details.push(isCondensed ? sunrise : `Sunrise: ${sunrise}`);
            }
            if (currentConfig.daily.sunset && weather.daily.sunset) {
                const sunset = new Date(weather.daily.sunset[i]).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                details.push(isCondensed ? sunset : `Sunset: ${sunset}`);
            }
            if (currentConfig.daily.daylight_duration && weather.daily.daylight_duration) {
                const daylight = formatDuration(weather.daily.daylight_duration[i]);
                details.push(isCondensed ? daylight : `Daylight: ${daylight}`);
            }
            if (currentConfig.daily.sunshine_duration && weather.daily.sunshine_duration) {
                const sunshine = formatDuration(weather.daily.sunshine_duration[i]);
                details.push(isCondensed ? sunshine : `Sunshine: ${sunshine}`);
            }
            if (currentConfig.daily.wind_speed_max && weather.daily.windspeed_10m_max) {
                const wind = `${convertWindSpeed(weather.daily.windspeed_10m_max[i])} ${currentConfig.units.wind_speed}`;
                details.push(isCondensed ? wind : `Wind: ${wind}`);
            }
            
            if (details.length > 0) {
                visualText += ` • ${details.join(' • ')}`;
            }
            
            html += `<div role="option" id="daily-item-${i}" aria-selected="${i === 0 ? 'true' : 'false'}" style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">${visualText}</div>`;
        }
        
        html += '</div>';
    } else {
        // Flat/Card view (default)
        html += '<ul class="forecast-grid">';
        
        for (let i = 0; i < 16 && i < weather.daily.time.length; i++) {
            const date = new Date(weather.daily.time[i]);
            let dayLabel;
            if (i === 0) {
                dayLabel = 'Today';
            } else {
                const weekday = date.toLocaleDateString(undefined, { weekday: 'short' });
                const monthDay = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                dayLabel = `${weekday}, ${monthDay}`;
            }
            
            html += '<li class="forecast-day">';
            html += `<strong>${dayLabel}</strong>`;
            html += `<p class="forecast-weather">${WEATHER_CODES[weather.daily.weathercode[i]] || 'Unknown'}</p>`;
            if (currentConfig.daily.temperature_max) html += `<p class="forecast-temp">High: ${convertTemperature(weather.daily.temperature_2m_max[i])}°${currentConfig.units.temperature}</p>`;
            if (currentConfig.daily.temperature_min) html += `<p class="forecast-temp">Low: ${convertTemperature(weather.daily.temperature_2m_min[i])}°${currentConfig.units.temperature}</p>`;
            
            if (currentConfig.daily.precipitation_sum) {
                html += `<p>Precip: ${convertPrecipitation(weather.daily.precipitation_sum[i])} ${currentConfig.units.precipitation}</p>`;
            }
            
            if (currentConfig.daily.precipitation_probability && weather.daily.precipitation_probability_max) {
                html += `<p>Precip Chance: ${weather.daily.precipitation_probability_max[i]}%</p>`;
            }
            
            if (currentConfig.daily.uv_index_max && weather.daily.uv_index_max && weather.daily.uv_index_max[i] !== null) {
                const { category } = getUVIndexCategory(weather.daily.uv_index_max[i]);
                html += `<p>UV: ${Math.round(weather.daily.uv_index_max[i])} (${category})</p>`;
            }
            
            if (currentConfig.daily.sunrise && weather.daily.sunrise) {
                const sunrise = new Date(weather.daily.sunrise[i]).toLocaleTimeString('en-US', { 
                    hour: 'numeric', minute: '2-digit', hour12: true 
                });
                html += `<p>Sunrise: ${sunrise}</p>`;
            }
            
            if (currentConfig.daily.sunset && weather.daily.sunset) {
                const sunset = new Date(weather.daily.sunset[i]).toLocaleTimeString('en-US', { 
                    hour: 'numeric', minute: '2-digit', hour12: true 
                });
                html += `<p>Sunset: ${sunset}</p>`;
            }
            
            if (currentConfig.daily.daylight_duration && weather.daily.daylight_duration) {
                html += `<p>Daylight: ${formatDuration(weather.daily.daylight_duration[i])}</p>`;
            }
            
            if (currentConfig.daily.sunshine_duration && weather.daily.sunshine_duration) {
                html += `<p>Sunshine: ${formatDuration(weather.daily.sunshine_duration[i])}</p>`;
            }
            
            if (currentConfig.daily.wind_speed_max && weather.daily.windspeed_10m_max) {
                html += `<p>Max Wind: ${convertWindSpeed(weather.daily.windspeed_10m_max[i])} ${currentConfig.units.wind_speed}</p>`;
            }
            
            html += '</li>';
        }
        
        html += '</ul>';
    }
    
    return html;
}

function closeWeatherDetailsDialog() {
    const dialog = document.getElementById('weather-details-dialog');
    dialog.hidden = true;
    if (focusReturnElement) {
        focusReturnElement.focus();
        focusReturnElement = null;
    }
}

// Configuration dialog
function openConfigDialog() {
    console.log('openConfigDialog called');
    try {
        const dialog = document.getElementById('config-dialog');
        console.log('Dialog element:', dialog);
        
        // Load current config into form
        Object.keys(currentConfig.current).forEach(key => {
            const checkbox = document.querySelector(`input[name="current-${key}"]`);
            if (checkbox) checkbox.checked = currentConfig.current[key];
        });
        
        Object.keys(currentConfig.hourly).forEach(key => {
            const checkbox = document.querySelector(`input[name="hourly-${key}"]`);
            if (checkbox) checkbox.checked = currentConfig.hourly[key];
        });
        
        Object.keys(currentConfig.daily).forEach(key => {
            const checkbox = document.querySelector(`input[name="daily-${key}"]`);
            if (checkbox) checkbox.checked = currentConfig.daily[key];
        });
        
        // Render city list order controls
        console.log('About to call renderCityListOrderControls');
        renderCityListOrderControls();
        console.log('renderCityListOrderControls completed');
        
        const tempUnit = document.querySelector(`input[name="temp-unit"][value="${currentConfig.units.temperature}"]`);
        if (tempUnit) tempUnit.checked = true;
        
        const windUnit = document.querySelector(`input[name="wind-unit"][value="${currentConfig.units.wind_speed}"]`);
        if (windUnit) windUnit.checked = true;
        
        const precipUnit = document.querySelector(`input[name="precip-unit"][value="${currentConfig.units.precipitation}"]`);
        if (precipUnit) precipUnit.checked = true;
        
        const pressureUnit = document.querySelector(`input[name="pressure-unit"][value="${currentConfig.units.pressure}"]`);
        if (pressureUnit) pressureUnit.checked = true;
        
        const distanceUnit = document.querySelector(`input[name="distance-unit"][value="${currentConfig.units.distance}"]`);
        if (distanceUnit) distanceUnit.checked = true;
        
        const defaultView = document.querySelector(`input[name="default-view"][value="${currentConfig.defaultView}"]`);
        if (defaultView) defaultView.checked = true;
        
        // List view style (may not exist in older configs)
        const listViewStyle = currentConfig.listViewStyle || 'detailed';
        const listViewStyleInput = document.querySelector(`input[name="list-view-style"][value="${listViewStyle}"]`);
        if (listViewStyleInput) listViewStyleInput.checked = true;
        
        // Detail view settings (may not exist in older configs)
        const currentConditionsView = currentConfig.currentConditionsView || 'flat';
        const currentConditionsViewInput = document.querySelector(`input[name="current-conditions-view"][value="${currentConditionsView}"]`);
        if (currentConditionsViewInput) currentConditionsViewInput.checked = true;
        
        const hourlyDetailView = currentConfig.hourlyDetailView || 'flat';
        const hourlyDetailViewInput = document.querySelector(`input[name="hourly-detail-view"][value="${hourlyDetailView}"]`);
        if (hourlyDetailViewInput) hourlyDetailViewInput.checked = true;
        
        const dailyDetailView = currentConfig.dailyDetailView || 'flat';
        const dailyDetailViewInput = document.querySelector(`input[name="daily-detail-view"][value="${dailyDetailView}"]`);
        if (dailyDetailViewInput) dailyDetailViewInput.checked = true;
        
        console.log('About to close modals and show dialog');
        closeAllModals();
        focusReturnElement = document.activeElement;
        dialog.hidden = false;
        trapFocus(dialog);
        document.getElementById('current-tab').focus();
        console.log('Dialog should now be visible');
    } catch (error) {
        console.error('Error in openConfigDialog:', error);
        alert('Error opening configuration dialog. Check console for details.');
    }
}

function applyConfiguration() {
    updateConfigFromForm();
    renderCityList();
    announceToScreenReader('Configuration applied');
}

function saveConfiguration() {
    updateConfigFromForm();
    saveConfigToStorage();
    renderCityList();
    closeConfigDialog();
    announceToScreenReader('Configuration saved');
}

function updateConfigFromForm() {
    // Current weather
    Object.keys(currentConfig.current).forEach(key => {
        const checkbox = document.querySelector(`input[name="current-${key}"]`);
        if (checkbox) currentConfig.current[key] = checkbox.checked;
    });
    
    // Hourly forecast
    Object.keys(currentConfig.hourly).forEach(key => {
        const checkbox = document.querySelector(`input[name="hourly-${key}"]`);
        if (checkbox) currentConfig.hourly[key] = checkbox.checked;
    });
    
    // Daily forecast
    Object.keys(currentConfig.daily).forEach(key => {
        const checkbox = document.querySelector(`input[name="daily-${key}"]`);
        if (checkbox) currentConfig.daily[key] = checkbox.checked;
    });
    
    // City list
    Object.keys(currentConfig.cityList).forEach(key => {
        const checkbox = document.querySelector(`input[name="citylist-${key}"]`);
        if (checkbox) currentConfig.cityList[key] = checkbox.checked;
    });
    
    // Units
    currentConfig.units.temperature = document.querySelector('input[name="temp-unit"]:checked').value;
    currentConfig.units.wind_speed = document.querySelector('input[name="wind-unit"]:checked').value;
    currentConfig.units.precipitation = document.querySelector('input[name="precip-unit"]:checked').value;
    currentConfig.units.pressure = document.querySelector('input[name="pressure-unit"]:checked').value;
    currentConfig.units.distance = document.querySelector('input[name="distance-unit"]:checked').value;
    
    // Default view
    currentConfig.defaultView = document.querySelector('input[name="default-view"]:checked').value;
    
    // List view style
    const listViewStyleChecked = document.querySelector('input[name="list-view-style"]:checked');
    if (listViewStyleChecked) {
        currentConfig.listViewStyle = listViewStyleChecked.value;
    }
    
    // Detail view settings
    const currentConditionsViewChecked = document.querySelector('input[name="current-conditions-view"]:checked');
    if (currentConditionsViewChecked) {
        currentConfig.currentConditionsView = currentConditionsViewChecked.value;
    }
    
    const hourlyDetailViewChecked = document.querySelector('input[name="hourly-detail-view"]:checked');
    if (hourlyDetailViewChecked) {
        currentConfig.hourlyDetailView = hourlyDetailViewChecked.value;
    }
    
    const dailyDetailViewChecked = document.querySelector('input[name="daily-detail-view"]:checked');
    if (dailyDetailViewChecked) {
        currentConfig.dailyDetailView = dailyDetailViewChecked.value;
    }
}

function renderCityListOrderControls() {
    const container = document.getElementById('citylist-order-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    const fieldLabels = {
        'temperature': 'Temperature',
        'conditions': 'Weather Conditions',
        'uv_index': 'UV Index',
        'feels_like': 'Feels Like',
        'humidity': 'Humidity',
        'wind_speed': 'Wind Speed',
        'wind_gusts': 'Wind Gusts',
        'wind_direction': 'Wind Direction',
        'high_temp': "Today's High",
        'low_temp': "Today's Low",
        'sunrise': 'Sunrise',
        'sunset': 'Sunset'
    };
    
    currentConfig.cityListOrder.forEach((key, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'order-item';
        itemDiv.dataset.key = key;
        
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = `citylist-${key}`;
        checkbox.checked = currentConfig.cityList[key];
        checkbox.setAttribute('aria-label', fieldLabels[key]);
        
        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(' ' + fieldLabels[key]));
        
        const controls = document.createElement('div');
        controls.className = 'order-controls';
        
        const upBtn = document.createElement('button');
        upBtn.type = 'button';
        upBtn.className = 'order-btn';
        upBtn.innerHTML = '↑';
        upBtn.setAttribute('aria-label', `Move ${fieldLabels[key]} up`);
        upBtn.disabled = index === 0;
        upBtn.addEventListener('click', () => moveCityListFieldUp(key));
        
        const downBtn = document.createElement('button');
        downBtn.type = 'button';
        downBtn.className = 'order-btn';
        downBtn.innerHTML = '↓';
        downBtn.setAttribute('aria-label', `Move ${fieldLabels[key]} down`);
        downBtn.disabled = index === currentConfig.cityListOrder.length - 1;
        downBtn.addEventListener('click', () => moveCityListFieldDown(key));
        
        controls.appendChild(upBtn);
        controls.appendChild(downBtn);
        
        itemDiv.appendChild(label);
        itemDiv.appendChild(controls);
        container.appendChild(itemDiv);
    });
}

function moveCityListFieldUp(key) {
    const index = currentConfig.cityListOrder.indexOf(key);
    if (index <= 0) return;
    
    const newOrder = [...currentConfig.cityListOrder];
    [newOrder[index - 1], newOrder[index]] = [newOrder[index], newOrder[index - 1]];
    currentConfig.cityListOrder = newOrder;
    
    renderCityListOrderControls();
    announceToScreenReader(`Moved ${key} up`);
}

function moveCityListFieldDown(key) {
    const index = currentConfig.cityListOrder.indexOf(key);
    if (index < 0 || index >= currentConfig.cityListOrder.length - 1) return;
    
    const newOrder = [...currentConfig.cityListOrder];
    [newOrder[index], newOrder[index + 1]] = [newOrder[index + 1], newOrder[index]];
    currentConfig.cityListOrder = newOrder;
    
    renderCityListOrderControls();
    announceToScreenReader(`Moved ${key} down`);
}

function closeConfigDialog() {
    const dialog = document.getElementById('config-dialog');
    dialog.hidden = true;
    if (focusReturnElement) {
        focusReturnElement.focus();
        focusReturnElement = null;
    }
}

// Reset functions
function resetCities() {
    if (!confirm('Are you sure you want to clear all cities? This cannot be undone.')) {
        return;
    }
    
    cities = {};
    weatherData = {};
    saveCitiesToStorage();
    renderCityList();
    announceToScreenReader('All cities have been cleared');
}

function resetSettings() {
    if (!confirm('Are you sure you want to reset all settings to default? This cannot be undone.')) {
        return;
    }
    
    currentConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
    saveConfigToStorage();
    
    // Update the config dialog if it's open
    renderCityListOrderControls();
    
    // Refresh the display
    renderCityList();
    announceToScreenReader('All settings have been reset to default');
}

function resetAll() {
    if (!confirm('Are you sure you want to reset everything? This will clear all cities and reset all settings to default. This cannot be undone.')) {
        return;
    }
    
    cities = {};
    weatherData = {};
    currentConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
    saveCitiesToStorage();
    saveConfigToStorage();
    
    // Update the config dialog if it's open
    renderCityListOrderControls();
    
    // Refresh the display
    renderCityList();
    announceToScreenReader('Everything has been reset');
}

// Debug functions
async function checkDebugStatus() {
    checkDebugLocalStorage();
    await checkDebugServiceWorker();
    await checkDebugCaches();
    await testDebugNetwork();
}

function checkDebugLocalStorage() {
    const output = document.getElementById('debug-storage-status');
    let html = '';
    
    // Check cities
    const citiesData = localStorage.getItem('fastweather-cities');
    html += '<strong>Cities:</strong>\n';
    if (citiesData) {
        try {
            const parsed = JSON.parse(citiesData);
            html += `✓ Found ${Object.keys(parsed).length} cities\n`;
            html += JSON.stringify(parsed, null, 2) + '\n';
        } catch (e) {
            html += `✗ Parse error: ${e.message}\n`;
        }
    } else {
        html += '⚠ No cities in localStorage (will use defaults)\n';
    }
    
    // Check config
    html += '\n<strong>Config:</strong>\n';
    const configData = localStorage.getItem('fastweather-config');
    if (configData) {
        try {
            const parsed = JSON.parse(configData);
            html += '✓ Config found\n';
            html += JSON.stringify(parsed, null, 2) + '\n';
        } catch (e) {
            html += `✗ Parse error: ${e.message}\n`;
        }
    } else {
        html += '⚠ No config (will use defaults)\n';
    }
    
    output.innerHTML = html;
}

async function checkDebugServiceWorker() {
    const output = document.getElementById('debug-sw-status');
    let html = '';
    
    if ('serviceWorker' in navigator) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        html += `<strong>Registered Service Workers:</strong> ${registrations.length}\n\n`;
        
        for (const reg of registrations) {
            html += `Scope: ${reg.scope}\n`;
            html += `State: ${reg.active ? 'active' : 'not active'}\n`;
            if (reg.active) {
                html += `Script: ${reg.active.scriptURL}\n`;
                html += `State: ${reg.active.state}\n`;
            }
            html += '\n';
        }
        
        if (registrations.length === 0) {
            html += '⚠ No service workers registered\n';
        }
    } else {
        html += '✗ Service Workers not supported\n';
    }
    
    output.innerHTML = html;
}

async function checkDebugCaches() {
    const output = document.getElementById('debug-cache-status');
    let html = '';
    
    if ('caches' in window) {
        const cacheNames = await caches.keys();
        html += `<strong>Active Caches:</strong> ${cacheNames.length}\n\n`;
        
        for (const cacheName of cacheNames) {
            const cache = await caches.open(cacheName);
            const keys = await cache.keys();
            html += `${cacheName}: ${keys.length} items\n`;
            
            // Show all URLs (limit to filename only for readability)
            const urls = keys.map(req => '  - ' + req.url.split('/').pop()).join('\n');
            html += urls + '\n';
            html += '\n';
        }
        
        if (cacheNames.length === 0) {
            html += '⚠ No caches found\n';
        }
    } else {
        html += '✗ Cache API not supported\n';
    }
    
    output.innerHTML = html;
}

async function testDebugNetwork() {
    const output = document.getElementById('debug-network-status');
    let html = '';
    
    // Test JSON file loads
    html += '<strong>Testing JSON file loads:</strong>\n\n';
    
    const files = [
        'us-cities-cached.json',
        'international-cities-cached.json',
        'places-of-the-world.json',
        'manifest.json'
    ];
    
    for (const file of files) {
        try {
            const response = await fetch(file);
            if (response.ok) {
                const size = response.headers.get('content-length');
                html += `✓ ${file}: ${response.status} ${response.statusText}${size ? ' (' + size + ' bytes)' : ''}\n`;
            } else {
                html += `✗ ${file}: ${response.status} ${response.statusText}\n`;
            }
        } catch (e) {
            html += `✗ ${file}: ${e.message}\n`;
        }
    }
    
    // Test weather API
    html += '\n<strong>Testing Weather API:</strong>\n';
    try {
        const response = await fetch('https://api.open-meteo.com/v1/forecast?latitude=43.074761&longitude=-89.3837613&current=temperature_2m&timezone=auto');
        if (response.ok) {
            const data = await response.json();
            html += `✓ Weather API: ${data.current.temperature_2m}°C\n`;
        } else {
            html += `✗ Weather API: ${response.status} ${response.statusText}\n`;
        }
    } catch (e) {
        html += `✗ Weather API: ${e.message}\n`;
    }
    
    output.innerHTML = html;
}

async function clearDebugCaches() {
    if (!confirm('This will clear all caches. Continue?')) {
        return;
    }
    
    try {
        if ('caches' in window) {
            const cacheNames = await caches.keys();
            for (const cacheName of cacheNames) {
                await caches.delete(cacheName);
            }
            alert('All caches cleared!');
            await checkDebugCaches();
        } else {
            alert('Cache API not supported');
        }
    } catch (e) {
        alert(`Error clearing caches: ${e.message}`);
    }
}

async function unregisterServiceWorker() {
    if (!confirm('This will unregister all service workers. Continue?')) {
        return;
    }
    
    try {
        if ('serviceWorker' in navigator) {
            const registrations = await navigator.serviceWorker.getRegistrations();
            for (const reg of registrations) {
                await reg.unregister();
            }
            alert('Service workers unregistered! Reload the page to continue.');
            await checkDebugServiceWorker();
        } else {
            alert('Service Workers not supported');
        }
    } catch (e) {
        alert(`Error unregistering service workers: ${e.message}`);
    }
}

// Unit conversion
function degreesToCardinal(degrees) {
    const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    const index = Math.round(degrees / 45) % 8;
    return directions[index];
}

function convertTemperature(celsius) {
    if (currentConfig.units.temperature === 'F') {
        return Math.round(celsius * 9/5 + 32);
    }
    return Math.round(celsius);
}

function convertWindSpeed(kmh) {
    if (currentConfig.units.wind_speed === 'mph') {
        return Math.round(kmh * KMH_TO_MPH);
    }
    return Math.round(kmh);
}

function convertPrecipitation(mm) {
    if (currentConfig.units.precipitation === 'in') {
        return (mm * MM_TO_INCHES).toFixed(2);
    }
    return mm.toFixed(1);
}

function convertPressure(hpa) {
    if (currentConfig.units.pressure === 'inHg') {
        return (hpa * HPA_TO_INHG).toFixed(2);
    }
    return hpa.toFixed(1);
}

function convertDistance(meters) {
    if (currentConfig.units.distance === 'mi') {
        return (meters * M_TO_MILES).toFixed(1);
    }
    return (meters * M_TO_KM).toFixed(1);
}

// UV Index helpers
function getUVIndexCategory(uvIndex) {
    if (uvIndex === null || uvIndex === undefined) return { category: 'Unknown', color: '#888' };
    if (uvIndex <= 2) return { category: 'Low', color: '#289500' };
    if (uvIndex <= 5) return { category: 'Moderate', color: '#f7e400' };
    if (uvIndex <= 7) return { category: 'High', color: '#f85900' };
    if (uvIndex <= 10) return { category: 'Very High', color: '#d8001d' };
    return { category: 'Extreme', color: '#6b49c8' };
}

function getUVIndexDescription(uvIndex) {
    if (uvIndex === null || uvIndex === undefined) return 'UV data unavailable';
    const { category } = getUVIndexCategory(uvIndex);
    let description = `UV Index: ${Math.round(uvIndex)} (${category})`;
    
    if (uvIndex <= 2) {
        description += ' - Minimal protection needed';
    } else if (uvIndex <= 5) {
        description += ' - Use SPF 30+ sunscreen';
    } else if (uvIndex <= 7) {
        description += ' - Use SPF 30+ sunscreen, seek shade';
    } else if (uvIndex <= 10) {
        description += ' - Use SPF 50+ sunscreen, avoid midday sun';
    } else {
        description += ' - Take all precautions, stay indoors if possible';
    }
    
    return description;
}

// Dew point helpers
function getDewPointComfort(dewPointF) {
    if (dewPointF === null || dewPointF === undefined) return 'Unknown';
    if (dewPointF < 50) return 'Dry';
    if (dewPointF < 60) return 'Comfortable';
    if (dewPointF < 65) return 'Slightly humid';
    if (dewPointF < 70) return 'Muggy/Uncomfortable';
    return 'Oppressive';
}

function formatDewPoint(dewPointC) {
    if (dewPointC === null || dewPointC === undefined) return 'N/A';
    const temp = convertTemperature(dewPointC);
    const comfort = getDewPointComfort(currentConfig.units.temperature === 'F' ? temp : (dewPointC * 9/5 + 32));
    return `${temp}°${currentConfig.units.temperature} (${comfort})`;
}

// Format duration (seconds to hours/minutes)
function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
}

// Storage
function loadCitiesFromStorage() {
    const stored = localStorage.getItem('fastweather-cities');
    if (stored) {
        try {
            cities = JSON.parse(stored);
        } catch (e) {
            console.error('Failed to load cities:', e);
            cities = {};
        }
    } else {
        // Load default cities
        cities = {
            "Madison, Wisconsin, United States": [43.074761, -89.3837613],
            "San Diego, California, United States": [32.7174202, -117.162772]
        };
    }
    
    // Fetch weather for all cities
    Object.entries(cities).forEach(([cityName, [lat, lon]]) => {
        fetchWeatherForCity(cityName, lat, lon, false, true); // silent = true on page load
    });
}

function saveCitiesToStorage() {
    try {
        localStorage.setItem('fastweather-cities', JSON.stringify(cities));
    } catch (e) {
        console.error('Failed to save cities to localStorage:', e);
        announceToScreenReader('Warning: Unable to save city list');
    }
}

function loadConfigFromStorage() {
    const stored = localStorage.getItem('fastweather-config');
    if (stored) {
        try {
            const loaded = JSON.parse(stored);
            currentConfig = loaded;
            // Ensure cityList exists for backward compatibility
            if (!currentConfig.cityList) {
                currentConfig.cityList = DEFAULT_CONFIG.cityList;
            }
            // Ensure cityListOrder exists for backward compatibility
            if (!currentConfig.cityListOrder) {
                currentConfig.cityListOrder = DEFAULT_CONFIG.cityListOrder;
            }
            // Ensure new cityList fields exist
            if (currentConfig.cityList.sunrise === undefined) {
                currentConfig.cityList.sunrise = false;
            }
            if (currentConfig.cityList.sunset === undefined) {
                currentConfig.cityList.sunset = false;
            }
            // Ensure pressure unit exists for backward compatibility
            if (!currentConfig.units.pressure) {
                currentConfig.units.pressure = DEFAULT_CONFIG.units.pressure;
            }
            // Ensure distance unit exists for backward compatibility
            if (!currentConfig.units.distance) {
                currentConfig.units.distance = DEFAULT_CONFIG.units.distance;
            }
            // Ensure defaultView exists for backward compatibility
            if (!currentConfig.defaultView) {
                currentConfig.defaultView = DEFAULT_CONFIG.defaultView;
            }
            // Ensure listViewStyle exists for backward compatibility
            if (!currentConfig.listViewStyle) {
                currentConfig.listViewStyle = DEFAULT_CONFIG.listViewStyle;
            }
        } catch (e) {
            console.error('Failed to load config:', e);
        }
    }
}

function saveConfigToStorage() {
    try {
        localStorage.setItem('fastweather-config', JSON.stringify(currentConfig));
    } catch (e) {
        console.error('Failed to save config to localStorage:', e);
        announceToScreenReader('Warning: Unable to save settings');
    }
}

// Utility functions
function showError(element, message) {
    element.textContent = message;
    element.classList.add('visible');
}

function clearError(element) {
    element.textContent = '';
    element.classList.remove('visible');
}

function announceToScreenReader(message) {
    const announcement = document.createElement('div');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    announcement.setAttribute('aria-atomic', 'true');
    announcement.className = 'visually-hidden';
    document.body.appendChild(announcement);
    
    // Add text after a brief delay to ensure screen readers detect the change
    setTimeout(() => {
        announcement.textContent = message;
    }, 100);
    
    // Remove after screen readers have had time to announce
    setTimeout(() => {
        if (announcement.parentNode) {
            document.body.removeChild(announcement);
        }
    }, 2000);
}

function closeAllModals() {
    document.querySelectorAll('.modal:not([hidden])').forEach(modal => {
        modal.hidden = true;
    });
    
    if (focusReturnElement) {
        focusReturnElement.focus();
        focusReturnElement = null;
    }
}

// Focus trap for modal dialogs
function trapFocus(element) {
    const focusableElements = element.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"]), [role="listbox"]'
    );
    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];
    
    element.addEventListener('keydown', function(e) {
        if (e.key !== 'Tab') return;
        
        if (e.shiftKey) {
            if (document.activeElement === firstFocusable) {
                lastFocusable.focus();
                e.preventDefault();
            }
        } else {
            if (document.activeElement === lastFocusable) {
                firstFocusable.focus();
                e.preventDefault();
            }
        }
    });
}
// ==================== NEW FEATURES ====================

// ===== WEATHER ALERTS (NWS API for US locations) =====
const alertsCache = {}; // Cache alerts by city key

async function fetchWeatherAlerts(cityKey, lat, lon) {
    console.log(`Fetching weather alerts for ${cityKey}...`);
    
    // Check cache first (10 minute cache)
    if (alertsCache[cityKey]) {
        const age = Date.now() - alertsCache[cityKey].timestamp;
        if (age < 600000) { // 10 minutes
            console.log(`Using cached alerts for ${cityKey}`);
            return alertsCache[cityKey].alerts;
        }
    }
    
    // NWS API only works for US locations
    // Simple heuristic: if the city key doesn't contain "United States", skip,
    // unless it's a saved US place from Places of the World ("Golden Gate
    // Bridge, San Francisco" names no country)
    if (!cityKey.includes('United States')) {
        await placesReady;
    }
    if (!cityKey.includes('United States') && !nwsPlaceNames.has(cityKey)) {
        console.log(`Skipping alerts for non-US city: ${cityKey}`);
        return [];
    }
    
    try {
        const url = `https://api.weather.gov/alerts/active?point=${lat},${lon}`;
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'FastWeather/1.1 Web'
            }
        });
        
        if (!response.ok) {
            console.log(`NWS alerts API returned ${response.status} for ${cityKey}`);
            return [];
        }
        
        const data = await response.json();
        const alerts = parseNWSAlerts(data);
        
        // Cache the results
        alertsCache[cityKey] = {
            alerts: alerts,
            timestamp: Date.now()
        };
        
        console.log(`Fetched ${alerts.length} alerts for ${cityKey}`);
        return alerts;
        
    } catch (error) {
        console.error(`Error fetching alerts for ${cityKey}:`, error);
        return [];
    }
}

function parseNWSAlerts(nwsResponse) {
    if (!nwsResponse || !nwsResponse.features) return [];
    
    const now = new Date();
    
    return nwsResponse.features.map(feature => {
        const props = feature.properties;
        
        // Parse severity
        const severityMap = {
            'Extreme': 'extreme',
            'Severe': 'severe',
            'Moderate': 'moderate',
            'Minor': 'minor'
        };
        const severity = severityMap[props.severity] || 'unknown';
        
        // Parse dates
        const onset = props.onset ? new Date(props.onset) : now;
        const expires = props.expires ? new Date(props.expires) : new Date(now.getTime() + 86400000);
        
        // Handle flexible string/array fields
        const getFlexibleField = (field) => {
            if (!field) return '';
            if (typeof field === 'string') return field;
            if (Array.isArray(field)) return field.join(' ');
            return '';
        };
        
        return {
            id: props.id,
            event: props.event || 'Weather Alert',
            severity: severity,
            headline: getFlexibleField(props.headline),
            description: getFlexibleField(props.description),
            instruction: getFlexibleField(props.instruction),
            onset: onset,
            expires: expires,
            areaDesc: getFlexibleField(props.areaDesc),
            isExpired: now > expires
        };
    }).filter(alert => !alert.isExpired); // Filter out expired alerts
}

function renderAlertBadge(alerts) {
    if (!alerts || alerts.length === 0) return '';
    
    // Find highest severity alert
    const severityOrder = ['extreme', 'severe', 'moderate', 'minor', 'unknown'];
    const highestSeverityAlert = alerts.reduce((highest, alert) => {
        const currentIndex = severityOrder.indexOf(alert.severity);
        const highestIndex = severityOrder.indexOf(highest.severity);
        return currentIndex < highestIndex ? alert : highest;
    }, alerts[0]);
    
    const severityIcons = {
        'extreme': '⚠️',
        'severe': '⚠️',
        'moderate': '⚠️',
        'minor': 'ℹ️',
        'unknown': 'ℹ️'
    };
    
    const icon = severityIcons[highestSeverityAlert.severity] || 'ℹ️';
    
    // Build screen reader label
    const srLabel = alerts.length === 1 
        ? `Weather alert: ${escapeHtml(highestSeverityAlert.event)}`
        : `${alerts.length} weather alerts: ${escapeHtml(highestSeverityAlert.event)} and ${alerts.length - 1} more`;
    
    return `<button class="alert-badge ${highestSeverityAlert.severity}" 
                    onclick="showAlertDetails('${encodeURIComponent(JSON.stringify(highestSeverityAlert))}')" 
                    aria-label="${srLabel}"
                    title="${escapeHtml(highestSeverityAlert.event)}">
                <span aria-hidden="true">${icon}</span>
            </button>`;
}

function showAlertDetails(alertDataStr) {
    const alert = JSON.parse(decodeURIComponent(alertDataStr));
    const dialog = document.getElementById('alert-details-dialog');
    const content = document.getElementById('alert-details-content');
    
    const severityIcons = {
        'extreme': '⚠️',
        'severe': '⚠️',
        'moderate': '⚠️',
        'minor': 'ℹ️',
        'unknown': 'ℹ️'
    };
    
    const icon = severityIcons[alert.severity] || 'ℹ️';
    
    content.innerHTML = `
        <div class="alert-details">
            <div class="alert-severity-header ${alert.severity}">
                <div class="alert-severity-icon" aria-hidden="true">${icon}</div>
                <div>
                    <div class="alert-event">${escapeHtml(alert.event)}</div>
                    <div class="alert-headline">${escapeHtml(alert.headline)}</div>
                </div>
            </div>
            
            <div class="alert-section">
                <h4>Details</h4>
                <p>${escapeHtml(alert.description)}</p>
            </div>
            
            ${alert.instruction ? `
                <div class="alert-section">
                    <h4>Instructions</h4>
                    <p>${escapeHtml(alert.instruction)}</p>
                </div>
            ` : ''}
            
            <div class="alert-meta">
                <div class="alert-meta-item">
                    <span class="alert-meta-label">Severity</span>
                    <span class="alert-meta-value">${alert.severity.charAt(0).toUpperCase() + alert.severity.slice(1)}</span>
                </div>
                <div class="alert-meta-item">
                    <span class="alert-meta-label">Onset</span>
                    <span class="alert-meta-value">${formatDateTime(alert.onset)}</span>
                </div>
                <div class="alert-meta-item">
                    <span class="alert-meta-label">Expires</span>
                    <span class="alert-meta-value">${formatDateTime(alert.expires)}</span>
                </div>
                ${alert.areaDesc ? `
                    <div class="alert-meta-item">
                        <span class="alert-meta-label">Areas Affected</span>
                        <span class="alert-meta-value">${escapeHtml(alert.areaDesc)}</span>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    closeAllModals();
    dialog.hidden = false;
    announceToScreenReader(`Weather alert: ${alert.event}. ${alert.severity} severity.`);
}

document.getElementById('close-alert-details-btn')?.addEventListener('click', () => {
    document.getElementById('alert-details-dialog').hidden = true;
});

// ===== HISTORICAL WEATHER =====
async function showHistoricalWeather(cityKey, lat, lon) {
    const dialog = document.getElementById('historical-weather-dialog');
    const content = document.getElementById('historical-weather-content');
    const title = document.getElementById('historical-weather-title');
    
    // Reset to current date when opening
    currentHistoricalDate = new Date();
    currentHistoricalCity = { key: cityKey, lat: lat, lon: lon };
    historicalYearOffset = 0; // Reset offset
    
    title.textContent = `Historical Weather - ${cityKey.split(',')[0]}`;
    
    const dateStr = currentHistoricalDate.toLocaleDateString('en-US', { 
        month: 'long', 
        day: 'numeric' 
    });
    
    content.innerHTML = `
        <div class="historical-controls">
            <div class="historical-date-nav">
                <button id="hist-prev-btn" onclick="adjustHistoricalYear(20)">← Previous 20 Years</button>
                <div class="historical-date-display" id="historical-current-date">${dateStr}</div>
                <button id="hist-next-btn" onclick="adjustHistoricalYear(-20)">Next 20 Years →</button>
            </div>
        </div>
        <div id="historical-data-container">
            <p>Loading historical weather data...</p>
        </div>
    `;
    
    closeAllModals();
    dialog.hidden = false;
    announceToScreenReader(`Historical weather for ${cityKey.split(',')[0]} - showing this day over the past 20 years`);
    
    // Automatically load data
    loadHistoricalData();
}

let currentHistoricalDate = new Date();
let currentHistoricalCity = null;
let historicalYearOffset = 0; // Tracks how many years to shift the 20-year window

async function loadHistoricalData() {
    if (!currentHistoricalCity) return;
    
    const container = document.getElementById('historical-data-container');
    container.innerHTML = '<p>Loading historical data...</p>';
    
    try {
        // Fetch the same month/day for 20 years, starting from offset
        const data = await fetchHistoricalWeatherMultiYear(
            currentHistoricalCity.lat, 
            currentHistoricalCity.lon, 
            currentHistoricalDate,
            20, // 20 years
            historicalYearOffset // Year offset for the window
        );
        
        renderHistoricalData(data);
        
    } catch (error) {
        container.innerHTML = `<p class="error-message">Error loading historical data: ${escapeHtml(error.message)}</p>`;
    }
}

async function fetchHistoricalWeatherSingleDay(lat, lon, date) {
    const url = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lon}&start_date=${date}&end_date=${date}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode&timezone=auto`;
    
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch historical data');
    
    return await response.json();
}

async function fetchHistoricalWeatherMultiYear(lat, lon, date, yearCount = 20, yearOffset = 0) {
    // Fetch the same month/day for N years, starting from offset
    const results = [];
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    for (let i = 0; i < yearCount; i++) {
        const year = date.getFullYear() - i - yearOffset;
        const dateStr = `${year}-${month}-${day}`;
        
        try {
            const data = await fetchHistoricalWeatherSingleDay(lat, lon, dateStr);
            if (data.daily) {
                results.push({
                    year: year,
                    date: dateStr,
                    temperature_2m_max: data.daily.temperature_2m_max[0],
                    temperature_2m_min: data.daily.temperature_2m_min[0],
                    precipitation_sum: data.daily.precipitation_sum[0],
                    weathercode: data.daily.weathercode[0]
                });
            }
        } catch (e) {
            console.error(`Failed to fetch data for ${dateStr}:`, e);
        }
    }
    
    return results;
}

function renderHistoricalData(data) {
    const container = document.getElementById('historical-data-container');
    
    if (!data || data.length === 0) {
        container.innerHTML = '<p>No historical data available for this date.</p>';
        return;
    }
    
    // Show loading for list view
    if (currentView === 'list') {
        container.innerHTML = '<p>Rendering historical data...</p>';
    } else {
        container.innerHTML = '';
    }
    
    // Render based on main page's current view mode
    if (currentView === 'table') {
        renderHistoricalTableView(container, data);
    } else if (currentView === 'flat') {
        renderHistoricalFlatView(container, data);
    } else if (currentView === 'list') {
        renderHistoricalListView(container, data);
    }
}

function renderHistoricalTableView(container, data) {
    const table = document.createElement('table');
    table.className = 'weather-table historical-table';
    
    // Table header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    ['Year', 'High', 'Low', 'Precipitation', 'Conditions'].forEach(text => {
        const th = document.createElement('th');
        th.textContent = text;
        th.scope = 'col';
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Table body
    const tbody = document.createElement('tbody');
    data.forEach(yearData => {
        const row = document.createElement('tr');
        
        // Year
        const yearCell = document.createElement('th');
        yearCell.scope = 'row';
        yearCell.textContent = yearData.year;
        row.appendChild(yearCell);
        
        // High
        const highCell = document.createElement('td');
        highCell.textContent = `${convertTemperature(yearData.temperature_2m_max)}°${currentConfig.units.temperature}`;
        row.appendChild(highCell);
        
        // Low
        const lowCell = document.createElement('td');
        lowCell.textContent = `${convertTemperature(yearData.temperature_2m_min)}°${currentConfig.units.temperature}`;
        row.appendChild(lowCell);
        
        // Precipitation
        const precipCell = document.createElement('td');
        precipCell.textContent = `${convertPrecipitation(yearData.precipitation_sum)} ${currentConfig.units.precipitation}`;
        row.appendChild(precipCell);
        
        // Conditions
        const condCell = document.createElement('td');
        condCell.textContent = WEATHER_CODES[yearData.weathercode] || 'Unknown';
        row.appendChild(condCell);
        
        tbody.appendChild(row);
    });
    table.appendChild(tbody);
    
    container.appendChild(table);
}

function renderHistoricalFlatView(container, data) {
    const grid = document.createElement('div');
    grid.className = 'city-grid';
    
    data.forEach(yearData => {
        const card = document.createElement('div');
        card.className = 'city-card historical-card';
        
        const high = convertTemperature(yearData.temperature_2m_max);
        const low = convertTemperature(yearData.temperature_2m_min);
        const precip = convertPrecipitation(yearData.precipitation_sum);
        const condition = WEATHER_CODES[yearData.weathercode] || 'Unknown';
        
        card.innerHTML = `
            <div class="city-card-header">
                <h3>${yearData.year}</h3>
            </div>
            <div class="city-card-body">
                <div class="weather-main">
                    <div class="temperature-display">
                        <span class="temp-large">H: ${high}°</span>
                        <span class="temp-large">L: ${low}°</span>
                    </div>
                    <div class="conditions">${condition}</div>
                </div>
                <div class="weather-details">
                    <div class="detail-item">
                        <span class="detail-label">Precipitation:</span>
                        <span class="detail-value">${precip} ${currentConfig.units.precipitation}</span>
                    </div>
                </div>
            </div>
        `;
        
        card.setAttribute('aria-label', `${yearData.year}: High ${high}, Low ${low}, ${condition}`);
        grid.appendChild(card);
    });
    
    container.appendChild(grid);
}

function renderHistoricalListView(container, data) {
    // Clear container first
    container.innerHTML = '';
    
    container.setAttribute('role', 'listbox');
    container.setAttribute('tabindex', '0');
    container.setAttribute('aria-label', 'Historical weather data - use arrow keys to navigate');
    
    const isCondensed = currentConfig.listViewStyle === 'condensed';
    
    data.forEach((yearData, index) => {
        const item = document.createElement('div');
        item.className = 'list-view-item historical-list-item';
        item.setAttribute('role', 'option');
        item.id = `hist-list-item-${index}`;
        item.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
        
        const high = convertTemperature(yearData.temperature_2m_max);
        const low = convertTemperature(yearData.temperature_2m_min);
        const precip = convertPrecipitation(yearData.precipitation_sum);
        const condition = WEATHER_CODES[yearData.weathercode] || 'Unknown';
        
        // Build parts array based on condensed/detailed style
        const parts = [];
        parts.push(isCondensed ? 
            `${high}°${currentConfig.units.temperature}` : 
            `High: ${high}°${currentConfig.units.temperature}`);
        parts.push(isCondensed ? 
            `${low}°${currentConfig.units.temperature}` : 
            `Low: ${low}°${currentConfig.units.temperature}`);
        parts.push(isCondensed ? condition : `Conditions: ${condition}`);
        parts.push(isCondensed ? 
            `${precip} ${currentConfig.units.precipitation}` : 
            `Precipitation: ${precip} ${currentConfig.units.precipitation}`);
        
        // Create concatenated string for screen reader
        const weatherText = `${yearData.year} - ${parts.join(', ')}`;
        
        // Create text node for main content
        const textNode = document.createTextNode(weatherText);
        item.appendChild(textNode);
        
        // Set aria-label for screen reader announcement
        item.setAttribute('aria-label', weatherText);
        
        container.appendChild(item);
    });
    
    // Set initial active descendant
    container.setAttribute('aria-activedescendant', 'hist-list-item-0');
    
    // Simple keyboard navigation for historical list
    const navHandler = (e) => {
        const items = container.querySelectorAll('.list-view-item');
        const currentActive = container.getAttribute('aria-activedescendant');
        let activeIndex = parseInt(currentActive.split('-').pop());
        
        let handled = false;
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (activeIndex < items.length - 1) {
                    activeIndex++;
                    items.forEach((item, i) => {
                        item.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
                    });
                    container.setAttribute('aria-activedescendant', `hist-list-item-${activeIndex}`);
                    announceToScreenReader(items[activeIndex].textContent);
                }
                handled = true;
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (activeIndex > 0) {
                    activeIndex--;
                    items.forEach((item, i) => {
                        item.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
                    });
                    container.setAttribute('aria-activedescendant', `hist-list-item-${activeIndex}`);
                    announceToScreenReader(items[activeIndex].textContent);
                }
                handled = true;
                break;
                
            case 'Home':
                e.preventDefault();
                activeIndex = 0;
                items.forEach((item, i) => {
                    item.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
                });
                container.setAttribute('aria-activedescendant', `hist-list-item-${activeIndex}`);
                announceToScreenReader(items[activeIndex].textContent);
                handled = true;
                break;
                
            case 'End':
                e.preventDefault();
                activeIndex = items.length - 1;
                items.forEach((item, i) => {
                    item.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
                });
                container.setAttribute('aria-activedescendant', `hist-list-item-${activeIndex}`);
                announceToScreenReader(items[activeIndex].textContent);
                handled = true;
                break;
        }
    };
    
    container.addEventListener('keydown', navHandler);
    
    // Set focus to the container now that it's fully rendered
    setTimeout(() => {
        container.focus();
        announceToScreenReader(`Historical data loaded, ${data.length} years`);
    }, 50);
}

function adjustHistoricalYear(yearShift) {
    historicalYearOffset += yearShift;
    
    // Prevent going into the future
    if (historicalYearOffset < 0) {
        historicalYearOffset = 0;
    }
    
    // Update button states
    const nextBtn = document.getElementById('hist-next-btn');
    const prevBtn = document.getElementById('hist-prev-btn');
    
    if (nextBtn) {
        // Disable next button if we're at the current period (offset = 0)
        nextBtn.disabled = historicalYearOffset === 0;
    }
    
    if (prevBtn) {
        // Always enable previous button (can go back indefinitely)
        prevBtn.disabled = false;
    }
    
    if (currentHistoricalCity) {
        loadHistoricalData();
    }
}

document.getElementById('close-historical-weather-btn')?.addEventListener('click', () => {
    document.getElementById('historical-weather-dialog').hidden = true;
});

// ===== PRECIPITATION NOWCAST =====
async function showPrecipitationNowcast(cityKey, lat, lon) {
    const dialog = document.getElementById('precipitation-nowcast-dialog');
    const content = document.getElementById('precipitation-nowcast-content');
    const title = document.getElementById('precipitation-nowcast-title');
    
    title.textContent = `Expected Precipitation - ${cityKey.split(',')[0]}`;
    content.innerHTML = '<p>Loading precipitation forecast...</p>';
    
    closeAllModals();
    dialog.hidden = false;
    
    try {
        const data = await fetchPrecipitationNowcast(lat, lon);
        renderPrecipitationNowcast(data);
        announceToScreenReader(`Precipitation forecast loaded for ${cityKey.split(',')[0]}`);
    } catch (error) {
        content.innerHTML = `<p class="error-message">Error loading precipitation data: ${escapeHtml(error.message)}</p>`;
    }
}

async function fetchPrecipitationNowcast(lat, lon) {
    const url = `${OPEN_METEO_API_URL}?latitude=${lat}&longitude=${lon}&minutely_15=precipitation&hourly=precipitation,weather_code&current=precipitation,weather_code&timezone=auto&forecast_days=1`;
    
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch precipitation data');
    
    return await response.json();
}

function renderPrecipitationNowcast(data) {
    const content = document.getElementById('precipitation-nowcast-content');
    
    if (!data.minutely_15 || !data.minutely_15.precipitation) {
        content.innerHTML = '<p>No precipitation forecast available</p>';
        return;
    }
    
    const now = new Date();
    const times = data.minutely_15.time;
    const precip = data.minutely_15.precipitation;
    
    // Find current time index
    let currentIndex = 0;
    for (let i = 0; i < times.length; i++) {
        const timeDate = new Date(times[i]);
        if (timeDate > now) {
            currentIndex = i;
            break;
        }
    }
    
    // Create visual timeline
    const intervals = [0, 15, 30, 45, 60, 90, 120]; // minutes from now
    let timelineHTML = '<div class="precipitation-timeline"><div class="precipitation-points">';
    
    intervals.forEach(interval => {
        const index = currentIndex + Math.floor(interval / 15);
        if (index >= 0 && index < precip.length) {
            const precipValue = precip[index] || 0;
            const height = Math.min(100, precipValue * 20); // Scale precipitation to pixels
            const label = interval === 0 ? 'Now' : `+${interval}m`;
            
            timelineHTML += `
                <div class="precip-point">
                    <div class="precip-bar" style="height: ${height}px"></div>
                    <div class="precip-label">${label}</div>
                </div>
            `;
        }
    });
    
    timelineHTML += '</div></div>';
    
    // Create data list for accessibility
    let dataListHTML = '<ul class="precipitation-data-list" aria-label="Precipitation forecast by time">';
    intervals.forEach(interval => {
        const index = currentIndex + Math.floor(interval / 15);
        if (index >= 0 && index < precip.length) {
            const precipValue = precip[index] || 0;
            const timeLabel = interval === 0 ? 'Now' : `In ${interval} minutes`;
            const precipStr = precipValue > 0.01 ? 
                `${convertPrecipitation(precipValue)} ${currentConfig.units.precipitation}` : 
                'None';
            
            dataListHTML += `<li>${timeLabel}: ${precipStr}</li>`;
        }
    });
    dataListHTML += '</ul>';
    
    content.innerHTML = `
        <div aria-hidden="true">${timelineHTML}</div>
        ${dataListHTML}
        <p style="margin-top: 1rem; font-size: 0.875rem; color: var(--text-secondary);">
            Data shows 15-minute interval precipitation forecasts for the next 2 hours.
        </p>
    `;
}

document.getElementById('close-precipitation-nowcast-btn')?.addEventListener('click', () => {
    document.getElementById('precipitation-nowcast-dialog').hidden = true;
});

// ===== WEATHER AROUND ME =====
async function showWeatherAroundMe(cityKey, lat, lon) {
    const dialog = document.getElementById('weather-around-me-dialog');
    const content = document.getElementById('weather-around-me-content');
    const title = document.getElementById('weather-around-me-title');
    
    title.textContent = `Weather Around ${cityKey.split(',')[0]}`;
    
    const distanceUnit = currentConfig.units.distance;
    const isKm = distanceUnit === 'km';
    
    // Define radius options for each unit
    const radiusOptions = isKm ? [
        { value: 80, label: '80 km' },
        { value: 160, label: '160 km' },
        { value: 240, label: '240 km', default: true },
        { value: 320, label: '320 km' },
        { value: 400, label: '400 km' }
    ] : [
        { value: 50, label: '50 miles' },
        { value: 100, label: '100 miles' },
        { value: 150, label: '150 miles', default: true },
        { value: 200, label: '200 miles' },
        { value: 250, label: '250 miles' }
    ];
    
    const optionsHtml = radiusOptions.map(opt => 
        `<option value="${opt.value}"${opt.default ? ' selected' : ''}>${opt.label}</option>`
    ).join('');
    
    content.innerHTML = `
        <div class="distance-selector">
            <label for="around-me-distance">Distance Radius:</label>
            <select id="around-me-distance" onchange="loadWeatherAroundMe('${cityKey}', ${lat}, ${lon}, this.value)">
                ${optionsHtml}
            </select>
        </div>
        <div id="weather-around-me-data">
            <p>Loading regional weather data...</p>
        </div>
    `;
    
    closeAllModals();
    dialog.hidden = false;
    
    // Default distance based on unit
    const defaultDistance = isKm ? 240 : 150;
    loadWeatherAroundMe(cityKey, lat, lon, defaultDistance);
}

async function loadWeatherAroundMe(cityKey, lat, lon, distance) {
    const container = document.getElementById('weather-around-me-data');
    container.innerHTML = '<p>Loading weather and location data...</p>';
    
    try {
        const distanceUnit = currentConfig.units.distance;
        const isKm = distanceUnit === 'km';
        
        // Convert to miles for calculation if needed (1 degree ≈ 69 miles)
        const distanceInMiles = isKm ? distance * 0.621371 : distance;
        const degreeOffset = distanceInMiles / 69;
        
        // Create 8 directional points
        const directions = [
            { name: 'North', lat: lat + degreeOffset, lon: lon, bearing: 0 },
            { name: 'Northeast', lat: lat + degreeOffset * 0.7, lon: lon + degreeOffset * 0.7, bearing: 45 },
            { name: 'East', lat: lat, lon: lon + degreeOffset, bearing: 90 },
            { name: 'Southeast', lat: lat - degreeOffset * 0.7, lon: lon + degreeOffset * 0.7, bearing: 135 },
            { name: 'South', lat: lat - degreeOffset, lon: lon, bearing: 180 },
            { name: 'Southwest', lat: lat - degreeOffset * 0.7, lon: lon - degreeOffset * 0.7, bearing: 225 },
            { name: 'West', lat: lat, lon: lon - degreeOffset, bearing: 270 },
            { name: 'Northwest', lat: lat + degreeOffset * 0.7, lon: lon - degreeOffset * 0.7, bearing: 315 }
        ];
        
        // Fetch weather for all directions in parallel (fast)
        const weatherPromises = directions.map(dir => fetchSimpleWeather(dir.lat, dir.lon));
        const weatherResults = await Promise.all(weatherPromises);
        
        // Reverse geocode sequentially to respect rate limits (1 req/sec for Nominatim)
        const results = [];
        for (let i = 0; i < directions.length; i++) {
            const dir = directions[i];
            const weather = weatherResults[i];
            
            // Add delay before each geocode request (except first)
            if (i > 0) {
                await new Promise(resolve => setTimeout(resolve, 1100)); // 1.1 second delay
            }
            
            const locationInfo = await reverseGeocode(dir.lat, dir.lon);
            const actualDistance = calculateDistanceMiles(lat, lon, dir.lat, dir.lon);
            
            results.push({
                direction: dir,
                weather: weather,
                locationInfo: locationInfo,
                actualDistance: actualDistance
            });
            
            // Update progress in UI
            container.innerHTML = `<p>Loading location data... (${i + 1}/${directions.length})</p>`;
        }
        
        // Render directional grid with city names and distances
        let html = '<div class="directional-grid">';
        results.forEach(result => {
            const dir = result.direction;
            const weather = result.weather;
            const locationInfo = result.locationInfo;
            
            if (weather && weather.current) {
                const temp = convertTemperature(weather.current.temperature_2m);
                const condition = WEATHER_CODES[weather.current.weather_code] || 'Unknown';
                
                // Build location display text
                let locationText = '';
                if (locationInfo && locationInfo.cityName) {
                    locationText = `<p class="location-name">${escapeHtml(locationInfo.cityName)}`;
                    if (locationInfo.state) {
                        locationText += `, ${escapeHtml(locationInfo.state)}`;
                    }
                    locationText += `</p>`;
                }
                
                const distanceUnit = currentConfig.units.distance;
                const isKm = distanceUnit === 'km';
                const displayDistance = result.actualDistance ? 
                    (isKm ? Math.round(result.actualDistance * 1.60934) : Math.round(result.actualDistance)) :
                    (isKm ? Math.round(distance * 1.60934) : Math.round(distance));
                const unitLabel = isKm ? 'km' : 'miles';
                
                const distanceText = `<p class="distance">${displayDistance} ${unitLabel} ${dir.name.toLowerCase()}</p>`;
                
                html += `
                    <div class="directional-sector">
                        <h4>${dir.name}</h4>
                        ${locationText}
                        ${distanceText}
                        <p class="temp">${temp}°${currentConfig.units.temperature}</p>
                        <p class="condition">${condition}</p>
                    </div>
                `;
            }
        });
        html += '</div>';
        
        // Add summary
        html += generateWeatherSummary(results.map(r => r.weather), cityKey);
        
        container.innerHTML = html;
        
        // Use distance unit for screen reader announcement
        const announceDistanceUnit = currentConfig.units.distance;
        const announceIsKm = announceDistanceUnit === 'km';
        const announceDisplayDistance = announceIsKm ? Math.round(distance * 1.60934) : Math.round(distance);
        const announceUnitLabel = announceIsKm ? 'kilometer' : 'mile';
        announceToScreenReader(`Regional weather loaded for ${announceDisplayDistance} ${announceUnitLabel} radius with location details`);
        
    } catch (error) {
        container.innerHTML = `<p class="error-message">Error loading regional weather: ${escapeHtml(error.message)}</p>`;
    }
}

async function fetchSimpleWeather(lat, lon) {
    const url = `${OPEN_METEO_API_URL}?latitude=${lat}&longitude=${lon}&current=temperature_2m,weather_code,precipitation&timezone=auto`;
    
    try {
        const response = await fetch(url);
        if (!response.ok) return null;
        return await response.json();
    } catch (e) {
        return null;
    }
}

/**
 * Calculate distance between two coordinates using Haversine formula
 * Returns distance in miles
 */
function calculateDistanceMiles(lat1, lon1, lat2, lon2) {
    const R = 3959; // Earth's radius in miles
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    const distance = R * c;
    
    return distance;
}

function generateWeatherSummary(weatherResults, cityKey) {
    // Analyze temperature and precipitation patterns
    const temps = weatherResults.filter(w => w && w.current).map(w => w.current.temperature_2m);
    const precips = weatherResults.filter(w => w && w.current).map(w => w.current.precipitation || 0);
    
    if (temps.length === 0) return '<p>Unable to generate summary</p>';
    
    const avgTemp = temps.reduce((a, b) => a + b, 0) / temps.length;
    const maxTemp = Math.max(...temps);
    const minTemp = Math.min(...temps);
    const hasPrecip = precips.some(p => p > 0.1);
    
    const avgTempConverted = convertTemperature(avgTemp);
    const maxTempConverted = convertTemperature(maxTemp);
    const minTempConverted = convertTemperature(minTemp);
    
    return `
        <div class="weather-summary-box">
            <h4>Regional Summary</h4>
            <p>Average temperature in surrounding area: ${avgTempConverted}°${currentConfig.units.temperature}</p>
            <p>Temperature range: ${minTempConverted}° to ${maxTempConverted}°${currentConfig.units.temperature}</p>
            ${hasPrecip ? '<p>Precipitation detected in one or more directions</p>' : '<p>No significant precipitation in the area</p>'}
        </div>
    `;
}

document.getElementById('close-weather-around-me-btn')?.addEventListener('click', () => {
    document.getElementById('weather-around-me-dialog').hidden = true;
});

// Helper function for date/time formatting
function formatDateTime(date) {
    if (!(date instanceof Date)) date = new Date(date);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

// HTML escaping for security
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') unsafe = String(unsafe);
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
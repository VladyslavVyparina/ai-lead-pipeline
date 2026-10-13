/**
 * Favicon Generator Script
 * 
 * This script generates all required favicon sizes from a source logo image.
 * 
 * Prerequisites:
 * npm install sharp
 * 
 * Usage:
 * node scripts/generate-favicons.js
 * 
 * Place your logo file as: public/logo-source.png (recommended: 512x512 or larger, square)
 */

const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const SOURCE_LOGO = path.join(PUBLIC_DIR, 'logo-source.png'); // Your source logo
const FAVICON_ICO = path.join(PUBLIC_DIR, 'favicon.ico'); // Keep existing if good

// Favicon sizes to generate
const SIZES = [
  { name: 'icon-16x16.png', size: 16 },
  { name: 'icon-32x32.png', size: 32 },
  { name: 'apple-touch-icon.png', size: 180 },
  { name: 'android-chrome-192x192.png', size: 192 },
  { name: 'android-chrome-512x512.png', size: 512 },
];

async function generateFavicons() {
  try {
    // Check if source logo exists
    if (!fs.existsSync(SOURCE_LOGO)) {
      console.error(`❌ Source logo not found: ${SOURCE_LOGO}`);
      console.log('\n📝 Please add your logo as: public/logo-source.png');
      console.log('   Recommended: Square image, 512x512 or larger, PNG format');
      return;
    }

    console.log('🎨 Generating favicons from:', SOURCE_LOGO);
    console.log('');

    // Get source image info
    const metadata = await sharp(SOURCE_LOGO).metadata();
    console.log(`📐 Source image: ${metadata.width}x${metadata.height}`);
    console.log('');

    // Generate each size
    for (const { name, size } of SIZES) {
      const outputPath = path.join(PUBLIC_DIR, name);
      
      await sharp(SOURCE_LOGO)
        .resize(size, size, {
          fit: 'contain',
          background: { r: 255, g: 255, b: 255, alpha: 0 } // Transparent background
        })
        .png()
        .toFile(outputPath);
      
      console.log(`✅ Generated: ${name} (${size}x${size})`);
    }

    console.log('');
    console.log('✨ All favicons generated successfully!');
    console.log('');
    console.log('📋 Next steps:');
    console.log('   1. Check the generated files in /public');
    console.log('   2. If needed, generate favicon.ico using: https://realfavicongenerator.net');
    console.log('   3. Generate OG image (1200x630) for social sharing');
    
  } catch (error) {
    console.error('❌ Error generating favicons:', error.message);
  }
}

// Run the script
generateFavicons();

/**
 * OG Image Generator Script
 * 
 * This script generates an Open Graph image (1200x630) for social sharing.
 * 
 * Prerequisites:
 * npm install sharp
 * 
 * Usage:
 * node scripts/generate-og-image.js
 * 
 * Place your logo/brand image as: public/logo-source.png
 */

const sharp = require('sharp');
const path = require('path');

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const SOURCE_LOGO = path.join(PUBLIC_DIR, 'logo-source.png');
const OG_IMAGE = path.join(PUBLIC_DIR, 'og-image.jpg');

// OG Image specifications
const OG_WIDTH = 1200;
const OG_HEIGHT = 630;

async function generateOGImage() {
  try {
    console.log('🎨 Generating Open Graph image...');
    console.log('');

    // Create a background with your brand color
    // Adjust the color to match your brand (currently using warm-sand)
    const background = await sharp({
      create: {
        width: OG_WIDTH,
        height: OG_HEIGHT,
        channels: 4,
        background: { r: 245, g: 240, b: 235, alpha: 1 } // warm-sand color
      }
    })
    .png()
    .toBuffer();

    // If you have a logo, composite it on top
    let image = sharp(background);

    // Optional: Add logo in center
    // Uncomment if you want to add your logo
    /*
    const logo = await sharp(SOURCE_LOGO)
      .resize(400, 400, { fit: 'contain' })
      .toBuffer();
    
    image = image.composite([{
      input: logo,
      gravity: 'center'
    }]);
    */

    // Save as JPEG with good quality
    await image
      .jpeg({ quality: 90 })
      .toFile(OG_IMAGE);

    console.log(`✅ Generated: og-image.jpg (${OG_WIDTH}x${OG_HEIGHT})`);
    console.log('');
    console.log('📋 Next steps:');
    console.log('   1. Customize the background color in this script');
    console.log('   2. Optionally add your logo by uncommenting the composite code');
    console.log('   3. Add text overlay using a design tool like Figma/Canva');
    console.log('   4. Recommended text: "Kaapora - Massagem Terapêutica no Porto"');
    
  } catch (error) {
    console.error('❌ Error generating OG image:', error.message);
  }
}

// Run the script
generateOGImage();

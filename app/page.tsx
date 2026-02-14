
import React from 'react';
import { ProductCard, Product } from '@/components/ProductCard';
import { LayoutGrid, ShoppingBag, TrendingUp, Filter } from 'lucide-react';
import { supabase } from '@/lib/supabase';

export const dynamic = 'force-dynamic';

async function getProducts(): Promise<Product[]> {
  const { data, error } = await supabase
    .from('nike_products')
    .select('*');

  if (error) {
    console.error('Supabase fetch error:', error.message);
    return [];
  }

  return (data ?? []) as Product[];
}

export default async function Home() {
  const products = await getProducts();
  const totalProducts = products.length;
  // Calculate average rating safely
  const validRatings = products.filter(p => !isNaN(Number(p.Rating_Score)) && Number(p.Rating_Score) > 0);
  const avgRating = validRatings.length > 0
    ? (validRatings.reduce((acc, p) => acc + Number(p.Rating_Score), 0) / validRatings.length).toFixed(1)
    : 'N/A';

  const categories = Array.from(new Set(products.map(p => p.Product_Description))).slice(0, 5);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-black text-white p-2 rounded-lg">
              <ShoppingBag className="w-5 h-5" />
            </div>
            <span className="text-xl font-bold tracking-tight">NikeScraper<span className="text-orange-600">.io</span></span>
          </div>
          <div className="flex items-center gap-6 text-sm font-medium text-gray-600">
            <div className="hidden md:flex items-center gap-6">
              <a href="#" className="text-gray-900">Dashboard</a>
              <a href="#" className="hover:text-black transition-colors">Analytics</a>
              <a href="#" className="hover:text-black transition-colors">Export</a>
            </div>
            <button className="px-5 py-2 bg-black text-white rounded-full text-sm font-bold hover:bg-gray-800 transition-transform hover:scale-105">
              Download CSV
            </button>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="bg-white border-b border-gray-100">
        <div className="container mx-auto px-6 py-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="bg-gray-50 p-6 rounded-2xl border border-gray-100">
              <div className="flex items-center gap-3 mb-2 text-gray-400">
                <ShoppingBag className="w-5 h-5" />
                <span className="text-sm font-bold uppercase tracking-wider">Total Products</span>
              </div>
              <div className="text-3xl font-black text-gray-900">{totalProducts}</div>
            </div>
            <div className="bg-orange-50 p-6 rounded-2xl border border-orange-100">
              <div className="flex items-center gap-3 mb-2 text-orange-400">
                <LayoutGrid className="w-5 h-5" />
                <span className="text-sm font-bold uppercase tracking-wider">Categories</span>
              </div>
              <div className="text-3xl font-black text-orange-900">{categories.length}+</div>
            </div>
            <div className="bg-blue-50 p-6 rounded-2xl border border-blue-100">
              <div className="flex items-center gap-3 mb-2 text-blue-400">
                <TrendingUp className="w-5 h-5" />
                <span className="text-sm font-bold uppercase tracking-wider">Avg Rating</span>
              </div>
              <div className="text-3xl font-black text-blue-900">{avgRating}</div>
            </div>
            <div className="bg-gray-900 p-6 rounded-2xl text-white">
              <div className="flex items-center gap-3 mb-2 text-gray-400">
                <Filter className="w-5 h-5" />
                <span className="text-sm font-bold uppercase tracking-wider">Filters</span>
              </div>
              <div className="text-sm text-gray-300">
                Showing all scraped products.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <main className="container mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-2xl font-bold text-gray-900">Live Product Feed</h2>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>Last updated just now</span>
          </div>
        </div>

        {products.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 bg-white rounded-3xl border border-gray-100 shadow-sm">
            <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4 text-gray-400">
              <LayoutGrid className="w-8 h-8" />
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">No Products Found</h3>
            <p className="text-gray-500 max-w-md text-center">
              The scraper hasn't finished or the CSV file is empty. Run the scraper logic to populate data.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
            {products.map((product, idx) => (
              <ProductCard key={idx} product={product} />
            ))}
          </div>
        )}
      </main>

      <footer className="bg-white border-t border-gray-100 py-12 mt-12">
        <div className="container mx-auto px-6 text-center text-gray-500 text-sm">
          <p className="mb-4 font-medium">Built with Next.js & Puppeteer</p>
          <p>&copy; {new Date().getFullYear()} Nike Scraper. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
